import io
import json
import os
import unittest
from unittest.mock import patch
from swarm_lab.providers import OpenAIProvider, ProviderFailure


class Response(io.BytesIO):
    headers={'x-request-id':'fixture-request'}


class ProviderTests(unittest.TestCase):
    def test_structured_response_request_and_usage_extraction(self):
        body={'id':'response-fixture','status':'completed','model':'test-model','service_tier':'default',
              'output':[{'type':'reasoning','content':[]},{'type':'message','content':[
                  {'type':'output_text','text':json.dumps({'candidate':[1,2,4],'message':None,'used_event_ids':[]})}]}],
              'usage':{'input_tokens':12,'output_tokens':8,'output_tokens_details':{'reasoning_tokens':3}}}
        with patch.dict(os.environ,{'OPENAI_API_KEY':'unit-test-placeholder'}):
            provider=OpenAIProvider('test-model',128)
            with patch('urllib.request.urlopen',return_value=Response(json.dumps(body).encode())) as call:
                result=provider.call({'m':4})
            request=call.call_args.args[0]
            payload=json.loads(request.data)
            self.assertEqual(payload['max_output_tokens'],128)
            self.assertFalse(payload['store'])
            self.assertNotIn('tools',payload)
            self.assertNotIn('unit-test-placeholder',request.data.decode())
            self.assertEqual(result.usage['output_tokens'],8)
            self.assertEqual(result.action['candidate'],[1,2,4])
            self.assertEqual(result.request_id,'fixture-request')

    def test_incomplete_response_still_preserves_usage(self):
        body={'status':'incomplete','usage':{'input_tokens':12,'output_tokens':128},'output':[]}
        with patch.dict(os.environ,{'OPENAI_API_KEY':'unit-test-placeholder'}):
            provider=OpenAIProvider('test-model',128)
            with patch('urllib.request.urlopen',return_value=Response(json.dumps(body).encode())):
                result=provider.call({'m':4})
        self.assertIsNone(result.action)
        self.assertEqual(result.usage['output_tokens'],128)
        self.assertEqual(result.outcome,'incomplete')

    def test_terra_request_carries_explicit_reasoning_timeout_and_private_auth(self):
        body={'status':'completed','output':[{'type':'message','content':[
            {'type':'output_text','text':json.dumps({'candidate':[1,2,4],'message':None,'used_event_ids':[]})}]}],
            'usage':{'input_tokens':12,'output_tokens':8,
                     'input_tokens_details':{'cached_tokens':2,'cache_write_tokens':4},
                     'output_tokens_details':{'reasoning_tokens':3}}}
        with patch('swarm_lab.providers.get_api_key',return_value='unit-test-placeholder') as load_key:
            provider=OpenAIProvider('gpt-5.6-terra',25000,120,reasoning_effort='medium')
        with patch.dict(os.environ,{'OPENAI_API_KEY':'changed-placeholder'}):
            with patch('urllib.request.urlopen',return_value=Response(json.dumps(body).encode())) as call:
                result=provider.call({'m':12})
        load_key.assert_called_once_with()
        request=call.call_args.args[0]
        payload=json.loads(request.data)
        self.assertEqual(payload['model'],'gpt-5.6-terra')
        self.assertEqual(payload['reasoning'],{'effort':'medium'})
        self.assertEqual(payload['max_output_tokens'],25000)
        self.assertEqual(call.call_args.kwargs['timeout'],120)
        self.assertEqual(request.get_header('Authorization'),'Bearer unit-test-placeholder')
        self.assertNotIn('placeholder',request.data.decode())
        self.assertEqual(result.usage['input_tokens_details']['cache_write_tokens'],4)
        self.assertEqual(result.usage['output_tokens_details']['reasoning_tokens'],3)
        self.assertEqual(provider.estimate({'m':12}),len(json.dumps(payload).encode('utf-8'))+1024)

    def test_auth_failure_prevents_construction_without_echoing_credential(self):
        with patch('swarm_lab.providers.get_api_key',side_effect=ValueError('Missing credential')):
            with patch('urllib.request.urlopen') as call:
                with self.assertRaisesRegex(ValueError,'Missing credential'):
                    OpenAIProvider('gpt-5.6-terra',25000,reasoning_effort='medium')
                call.assert_not_called()

    def test_transport_exception_does_not_expose_auth_details(self):
        with patch('swarm_lab.providers.get_api_key',return_value='unit-test-placeholder'):
            provider=OpenAIProvider('gpt-5.6-terra',25000,reasoning_effort='medium')
        with patch('urllib.request.urlopen',side_effect=OSError('unit-test-placeholder')):
            with self.assertRaises(ProviderFailure) as failure:
                provider.call({'m':12})
        self.assertEqual(str(failure.exception),'transport_unknown')
