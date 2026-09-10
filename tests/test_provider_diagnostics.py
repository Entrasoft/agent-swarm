"""Transport and response failures remain diagnosable without logging their text."""
import io
import http.client
import json
import unittest
import urllib.error
from unittest.mock import patch

from swarm_lab.providers import OpenAIProvider, ProviderFailure, ProviderResult


SECRET = 'unit-test-sensitive-placeholder'
CLIENT_ID = 'b4cb661f-887e-4359-a913-3eab0cffd9e5'
USAGE = {'input_tokens': 12, 'output_tokens': 8, 'total_tokens': 20,
         'input_tokens_details': {'cached_tokens': 2, 'cache_write_tokens': 1},
         'output_tokens_details': {'reasoning_tokens': 3}}


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, request_id='req_fixture'):
        super().__init__(body)
        self.headers = {'x-request-id': request_id, 'Authorization': 'Bearer '+SECRET}


class ProviderDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        with patch('swarm_lab.providers.get_api_key', return_value=SECRET):
            self.provider = OpenAIProvider('test-model', 128)

    def body(self, **updates):
        body = {'id': 'resp_fixture', 'status': 'completed', 'model': 'test-model',
                'service_tier': 'default', 'usage': USAGE,
                'output': [{'type': 'message', 'content': [{'type': 'output_text',
                    'text': json.dumps({'candidate': [1, 2, 4], 'message': None,
                                        'used_event_ids': []})}]}]}
        body.update(updates)
        return body

    def call(self, body):
        with patch('urllib.request.urlopen', return_value=Response(json.dumps(body).encode())):
            return self.provider.call_with_id({'m': 4}, CLIENT_ID)

    def assert_safe(self, value):
        text = json.dumps(value, sort_keys=True)
        self.assertNotIn(SECRET, text)
        self.assertNotIn('Authorization', text)
        self.assertNotIn('Bearer', text)
        self.assertLess(len(text), 4096)

    def test_client_id_is_a_header_and_payload_stays_identical(self):
        with patch('urllib.request.urlopen', return_value=Response(json.dumps(self.body()).encode())) as send:
            result = self.provider.call_with_id({'m': 4}, CLIENT_ID)
        request = send.call_args.args[0]
        self.assertEqual(request.get_header('X-client-request-id'), CLIENT_ID)
        self.assertNotIn(CLIENT_ID, request.data.decode())
        self.assertEqual(json.loads(request.data), self.provider.payload({'m': 4}))
        self.assertEqual(result.diagnostics['client_request_id'], CLIENT_ID)
        self.assertEqual(result.request_id, 'req_fixture')
        self.assertEqual(result.diagnostics['request_id_source'], 'response_header')
        self.assertEqual(result.diagnostics['response_id'], 'resp_fixture')
        self.assertEqual(result.usage, USAGE)
        self.assert_safe(result.diagnostics)

    def test_legacy_call_requires_no_correlation_argument(self):
        with patch('urllib.request.urlopen', return_value=Response(json.dumps(self.body()).encode())) as send:
            result = self.provider.call({'m': 4})
        self.assertIsNone(send.call_args.args[0].get_header('X-client-request-id'))
        self.assertEqual(result.action['candidate'], [1, 2, 4])

    def test_missing_header_uses_explicitly_identified_response_id_fallback(self):
        with patch('urllib.request.urlopen', return_value=Response(json.dumps(self.body()).encode(), None)):
            result = self.provider.call({'m': 4})
        self.assertEqual(result.request_id, 'resp_fixture')
        self.assertEqual(result.diagnostics['response_id'], 'resp_fixture')
        self.assertEqual(result.diagnostics['request_id_source'], 'response_id_fallback')
        self.assertTrue(result.diagnostics['response_headers_received'])

    def test_missing_header_and_response_id_remain_unavailable(self):
        with patch('urllib.request.urlopen', return_value=Response(json.dumps(self.body(id=None)).encode(), None)):
            result = self.provider.call({'m': 4})
        self.assertIsNone(result.request_id)
        self.assertEqual(result.diagnostics['request_id_source'], 'unavailable')

    def test_invalid_client_identifier_is_rejected_before_transport(self):
        for value in ('', 'x'*513, 'id\r\nAuthorization: secret', 'unicode-é', SECRET, None):
            with self.subTest(value_type=type(value).__name__), patch('urllib.request.urlopen') as send:
                with self.assertRaisesRegex(ValueError, '^Invalid client request identifier.$'):
                    self.provider.call_with_id({'m': 4}, value)
                send.assert_not_called()

    def test_refusal_is_distinct_and_keeps_usage_without_refusal_text(self):
        result = self.call(self.body(output=[{'type': 'message', 'content': [
            {'type': 'refusal', 'refusal': SECRET}]}]))
        self.assertEqual(result.outcome, 'invalid_action')
        self.assertEqual(result.diagnostics['failure_category'], 'refusal')
        self.assertEqual(result.diagnostics['content_types'], ['refusal'])
        self.assertEqual(result.diagnostics['refusal_count'], 1)
        self.assertEqual(result.usage, USAGE)
        self.assertIsNone(result.action)
        self.assert_safe(result.diagnostics)

    def test_refusal_plus_output_does_not_admit_action(self):
        body = self.body()
        body['output'][0]['content'].append({'type': 'refusal', 'refusal': SECRET})
        result = self.call(body)
        self.assertIsNone(result.action)
        self.assertEqual(result.diagnostics['failure_category'], 'refusal')

    def test_incomplete_reasoning_keeps_reason_and_usage_without_reasoning(self):
        result = self.call(self.body(status='incomplete',
            incomplete_details={'reason': 'max_output_tokens', 'extra': SECRET},
            output=[{'type': 'reasoning', 'summary': [{'text': SECRET}],
                     'encrypted_content': SECRET}]))
        self.assertEqual(result.outcome, 'incomplete')
        self.assertEqual(result.diagnostics['incomplete_reason'], 'max_output_tokens')
        self.assertEqual(result.diagnostics['output_item_types'], ['reasoning'])
        self.assertEqual(result.diagnostics['output_text_chars'], 0)
        self.assertEqual(result.usage, USAGE)
        self.assert_safe(result.diagnostics)

    def test_invalid_output_json_retains_only_parse_location(self):
        result = self.call(self.body(output=[{'type': 'message', 'content': [
            {'type': 'output_text', 'text': '{"candidate": '+SECRET}]}]))
        self.assertEqual(result.outcome, 'invalid_action')
        self.assertEqual(result.diagnostics['failure_category'], 'invalid_output_json')
        self.assertEqual(result.diagnostics['parse_error'], 'json_decode_error')
        self.assertIn('parse_position', result.diagnostics)
        self.assertEqual(result.usage, USAGE)
        self.assertIsNone(result.action)
        self.assert_safe(result.diagnostics)

    def test_empty_output_and_nonobject_action_are_distinct(self):
        for text, category in (('', 'empty_output'), (' \n ', 'empty_output'),
                               ('[]', 'action_not_object'), ('null', 'action_not_object')):
            with self.subTest(category=category):
                result = self.call(self.body(output=[{'type': 'message', 'content': [
                    {'type': 'output_text', 'text': text}]}]))
                self.assertIsNone(result.action)
                self.assertEqual(result.diagnostics['failure_category'], category)
                self.assertEqual(result.usage, USAGE)

    def test_malformed_json_envelope_retains_server_id(self):
        with patch('urllib.request.urlopen', return_value=Response(('{ '+SECRET).encode())):
            with self.assertRaises(ProviderFailure) as caught:
                self.provider.call_with_id({'m': 4}, CLIENT_ID)
        failure = caught.exception
        self.assertEqual(failure.outcome, 'malformed_response_unknown')
        self.assertEqual(failure.request_id, 'req_fixture')
        self.assertEqual(failure.diagnostics['request_id_source'], 'response_header')
        self.assertEqual(failure.diagnostics['client_request_id'], CLIENT_ID)
        self.assertEqual(failure.diagnostics['failure_category'], 'malformed_response_json')
        self.assert_safe(failure.diagnostics)
        self.assertNotIn(SECRET, str(failure))

    def test_invalid_top_level_envelopes_fail_closed(self):
        for body in ([], [SECRET], SECRET, None, 42):
            with self.subTest(body_type=type(body).__name__):
                with patch('urllib.request.urlopen', return_value=Response(json.dumps(body).encode())):
                    with self.assertRaises(ProviderFailure) as caught:
                        self.provider.call({'m': 4})
                self.assertEqual(caught.exception.request_id, 'req_fixture')
                self.assertEqual(caught.exception.diagnostics['failure_category'], 'invalid_envelope')
                self.assert_safe(caught.exception.diagnostics)

    def test_invalid_output_structures_preserve_usage(self):
        for output in (None, {}, [None], [{'type': 'message', 'content': None}],
                       [{'type': 'message', 'content': [None]}],
                       [{'type': 'message', 'content': [{'type': 'output_text', 'text': [SECRET]}]}]):
            with self.subTest(output_type=type(output).__name__):
                result = self.call(self.body(output=output))
                self.assertEqual(result.outcome, 'invalid_action')
                self.assertEqual(result.diagnostics['failure_category'], 'invalid_envelope')
                self.assertEqual(result.usage, USAGE)
                self.assert_safe(result.diagnostics)

    def test_timeout_and_connection_failure_keep_client_id_without_error_text(self):
        for error, category in ((TimeoutError(SECRET), 'transport_timeout'),
                               (urllib.error.URLError(TimeoutError(SECRET)), 'transport_timeout'),
                               (ConnectionError(SECRET), 'transport_connection'),
                               (urllib.error.URLError(SECRET), 'transport_connection')):
            with self.subTest(error_type=type(error).__name__):
                with patch('urllib.request.urlopen', side_effect=error):
                    with self.assertRaises(ProviderFailure) as caught:
                        self.provider.call_with_id({'m': 4}, CLIENT_ID)
                failure = caught.exception
                self.assertEqual(failure.outcome, 'transport_unknown')
                self.assertIsNone(failure.request_id)
                self.assertEqual(failure.diagnostics['request_id_source'], 'unavailable')
                self.assertEqual(failure.diagnostics['failure_category'], category)
                self.assertEqual(failure.diagnostics['client_request_id'], CLIENT_ID)
                self.assertFalse(failure.diagnostics['response_headers_received'])
                self.assert_safe(failure.diagnostics)
                self.assertNotIn(SECRET, str(failure))

    def test_timeout_reading_body_retains_server_id(self):
        response = Response(b'')
        with patch.object(response, 'read', side_effect=TimeoutError(SECRET)):
            with patch('urllib.request.urlopen', return_value=response):
                with self.assertRaises(ProviderFailure) as caught:
                    self.provider.call_with_id({'m': 4}, CLIENT_ID)
        self.assertEqual(caught.exception.request_id, 'req_fixture')
        self.assertEqual(caught.exception.diagnostics['request_id_source'], 'response_header')
        self.assertTrue(caught.exception.diagnostics['response_headers_received'])
        self.assertEqual(caught.exception.diagnostics['failure_category'], 'transport_timeout')
        self.assert_safe(caught.exception.diagnostics)

    def test_truncated_http_body_retains_server_id_without_partial_body(self):
        response = Response(b'')
        with patch.object(response, 'read', side_effect=http.client.IncompleteRead(SECRET.encode())):
            with patch('urllib.request.urlopen', return_value=response):
                with self.assertRaises(ProviderFailure) as caught:
                    self.provider.call_with_id({'m': 4}, CLIENT_ID)
        self.assertEqual(caught.exception.request_id, 'req_fixture')
        self.assertEqual(caught.exception.outcome, 'transport_unknown')
        self.assertEqual(caught.exception.diagnostics['failure_category'], 'transport_protocol')
        self.assert_safe(caught.exception.diagnostics)

    def test_invalid_response_encoding_retains_server_id(self):
        with patch('urllib.request.urlopen', return_value=Response(b'\xff\xfe\xff')):
            with self.assertRaises(ProviderFailure) as caught:
                self.provider.call_with_id({'m': 4}, CLIENT_ID)
        self.assertEqual(caught.exception.request_id, 'req_fixture')
        self.assertEqual(caught.exception.outcome, 'malformed_response_unknown')
        self.assertEqual(caught.exception.diagnostics['failure_category'], 'malformed_response_encoding_or_shape')

    def test_http_error_retains_status_and_ids_without_reading_body(self):
        error = urllib.error.HTTPError('https://api.openai.com/v1/responses', 429, SECRET,
            {'x-request-id': 'req_failed', 'Authorization': SECRET}, io.BytesIO(SECRET.encode()))
        with patch.object(error, 'read') as read:
            with patch('urllib.request.urlopen', side_effect=error):
                with self.assertRaises(ProviderFailure) as caught:
                    self.provider.call_with_id({'m': 4}, CLIENT_ID)
            read.assert_not_called()
        self.assertEqual(caught.exception.outcome, 'http_429')
        self.assertEqual(caught.exception.request_id, 'req_failed')
        self.assertEqual(caught.exception.diagnostics['request_id_source'], 'response_header')
        self.assertEqual(caught.exception.diagnostics['http_status'], 429)
        self.assert_safe(caught.exception.diagnostics)
        self.assertNotIn(SECRET, str(caught.exception))

    def test_unknown_metadata_is_mapped_to_bounded_labels(self):
        result = self.call(self.body(status=SECRET, incomplete_details={'reason': SECRET},
            error={'message': SECRET, 'code': SECRET},
            output=[{'type': SECRET}, {'type': 'message', 'content': [{'type': SECRET}]}]))
        self.assertEqual(result.outcome, 'unknown')
        self.assertEqual(result.diagnostics['incomplete_reason'], 'other')
        self.assertEqual(result.diagnostics['output_item_types'], ['message', 'other'])
        self.assertEqual(result.diagnostics['content_types'], ['other'])
        self.assert_safe(result.diagnostics)

    def test_response_identifiers_cannot_echo_credentials_or_header_lines(self):
        for value in (SECRET, 'sk-placeholder', 'req\r\nAuthorization: '+SECRET, 'x'*513):
            with self.subTest(identifier_length=len(value)):
                body = self.body(id=value, model=value, service_tier=value)
                with patch('urllib.request.urlopen', return_value=Response(json.dumps(body).encode(), value)):
                    result = self.provider.call({'m': 4})
                self.assertIsNone(result.request_id)
                self.assertIsNone(result.model)
                self.assertIsNone(result.service_tier)
                self.assert_safe(result.diagnostics)

    def test_usage_telemetry_whitelists_only_numeric_accounting_fields(self):
        usage = dict(USAGE, arbitrary_public_text=SECRET,
                     input_tokens_details=dict(USAGE['input_tokens_details'], secret_field=SECRET),
                     output_tokens_details=dict(USAGE['output_tokens_details'], private_reasoning=SECRET))
        result = self.call(self.body(usage=usage))
        self.assertEqual(result.usage, USAGE)
        self.assert_safe(result.usage)
        self.assert_safe(result.diagnostics)

    def test_missing_usage_fields_stay_missing_and_invalid_counters_stay_unknown(self):
        for usage in ({'input_tokens': 12}, {'output_tokens': 8, 'input_tokens_details': None}, {}):
            with self.subTest(usage=usage):
                result = self.call(self.body(usage=usage))
                self.assertEqual(result.usage, usage)
        for usage in (SECRET, {'input_tokens': SECRET}, {'input_tokens': True},
                      {'input_tokens': -1}, {'input_tokens_details': []},
                      {'input_tokens_details': {'cached_tokens': SECRET}},
                      dict(USAGE, total_tokens=21),
                      dict(USAGE, input_tokens_details={'cached_tokens': 10, 'cache_write_tokens': 4}),
                      dict(USAGE, output_tokens_details={'reasoning_tokens': 9})):
            with self.subTest(usage_type=type(usage).__name__):
                result = self.call(self.body(usage=usage))
                self.assertIsNone(result.usage)
                self.assertEqual(result.diagnostics['usage_metadata'], 'invalid')
                self.assert_safe(result.diagnostics)

    def test_compatibility_defaults_are_separate_mutable_objects(self):
        first, second = ProviderResult(None, None), ProviderResult(None, None)
        first.diagnostics['test'] = True
        self.assertEqual(second.diagnostics, {})
        failure = ProviderFailure('transport_unknown')
        self.assertEqual(failure.diagnostics, {})


if __name__ == '__main__':
    unittest.main()
