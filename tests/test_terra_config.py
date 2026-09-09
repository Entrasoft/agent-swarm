"""Live configuration boundaries tested without API calls or credentials."""
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from swarm_lab.cli import main
from swarm_lab.providers import ProviderResult
from swarm_lab.runtime import OFFLINE_PRICE, RunConfig, Runtime


def terra_price(model='gpt-5.6-terra'):
    return dict(OFFLINE_PRICE,provider='openai',model=model,simulated=False,
                input_per_million='2',cached_input_per_million='0.2',
                cache_write_per_million='2.5',output_per_million='12',
                source_url='https://developers.openai.com/api/docs/pricing',
                verified_on=time.strftime('%Y-%m-%d'))


def live_config(**changes):
    config=dict(mode='live',allow_live=True,agents=1,condition='solo',steps=1,
                concurrency=1,max_retries=0,model='gpt-5.6-terra',price=terra_price(),
                token_limit=100000,cost_limit='2',max_output=25000,timeout_seconds=120)
    config.update(changes)
    return RunConfig(**config)


class TerraConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)

    def test_old_three_bucket_price_cannot_dispatch_terra(self):
        for model in ('gpt-5.6-terra','gpt-5.6-terra-2026-09-01'):
            with self.subTest(model=model):
                price=terra_price(model)
                del price['cache_write_per_million']
                with patch('swarm_lab.runtime.OpenAIProvider') as provider:
                    with self.assertRaisesRegex(ValueError,'complete'):
                        Runtime(live_config(model=model,price=price),self.base/'blocked')
                    provider.assert_not_called()
                self.assertFalse((self.base/'blocked').exists())

    def test_live_reasoning_default_is_forwarded_and_persisted(self):
        class FakeProvider:
            def estimate(self,observation): return 100
            def call(self,observation):
                return ProviderResult({'candidate':[1,2,4],'message':None,'used_event_ids':[]},
                    {'input_tokens':20,'output_tokens':10,
                     'input_tokens_details':{'cached_tokens':0,'cache_write_tokens':0}})
        config=live_config()
        with patch('swarm_lab.runtime.OpenAIProvider',return_value=FakeProvider()) as provider:
            result=asyncio.run(Runtime(config,self.base/'live').run())
        provider.assert_called_once_with('gpt-5.6-terra',25000,120,reasoning_effort='medium')
        saved=json.loads((self.base/'live'/'config.json').read_text())
        self.assertEqual(saved['reasoning_effort'],'medium')
        self.assertEqual(saved['timeout_seconds'],120)
        self.assertEqual(result['actual_model_calls'],1)
        self.assertEqual(result['lower_bound'],3)

    def test_invalid_reasoning_timeout_and_price_metadata_fail_before_auth(self):
        cases=[{'reasoning_effort':'automatic'},{'timeout_seconds':121},
               {'price':dict(terra_price(),api_key='unit-test-placeholder')}]
        for changes in cases:
            with self.subTest(changes=changes):
                with patch('swarm_lab.runtime.OpenAIProvider') as provider:
                    with self.assertRaises(ValueError):
                        Runtime(live_config(**changes),self.base/'blocked')
                    provider.assert_not_called()
                self.assertFalse((self.base/'blocked').exists())

    def test_cli_forwards_explicit_pilot_configuration(self):
        price_path=self.base/'price.json'
        price_path.write_text(json.dumps(terra_price()))
        summary=dict(run_id='fixture',mode='live',lower_bound=3,upper_bound=6,gap=3,
                     stopping_reason='step_limit',actual_model_calls=0,actual_model_cost='0')
        with patch('swarm_lab.cli.Runtime') as runtime:
            runtime.return_value.run=AsyncMock(return_value=summary)
            with redirect_stdout(io.StringIO()):
                main(['run','--mode','live','--allow-live','--model','gpt-5.6-terra',
                      '--agents','1','--condition','solo','--steps','3','--concurrency','1',
                      '--reasoning-effort','high','--timeout','120','--max-output','25000',
                      '--max-retries','0','--token-limit','100000','--cost-limit','2',
                      '--price-file',str(price_path),'--out',str(self.base/'pilot')])
        config=runtime.call_args.args[0]
        config.validate()
        self.assertEqual((config.reasoning_effort,config.timeout_seconds),('high',120))
        self.assertEqual((config.steps,config.max_retries,config.max_output),(3,0,25000))
        self.assertEqual((config.cost_limit,config.token_limit),('2',100000))

    def test_offline_keeps_simulated_prices_and_omits_reasoning_requests(self):
        config=RunConfig(steps=1,agents=1,condition='solo')
        with patch('swarm_lab.runtime.OpenAIProvider') as provider:
            result=asyncio.run(Runtime(config,self.base/'offline').run())
            provider.assert_not_called()
        self.assertIsNone(config.reasoning_effort)
        self.assertEqual(config.price,OFFLINE_PRICE)
        self.assertEqual(result['actual_model_calls'],0)


if __name__=='__main__':
    unittest.main()
