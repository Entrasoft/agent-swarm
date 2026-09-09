import io
import json
import os
import unittest
from unittest.mock import patch
from swarm_lab.providers import OpenAIProvider


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
