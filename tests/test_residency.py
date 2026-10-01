import unittest
from unittest.mock import patch
from ml.residency import ResidencyController


class FakeTransport:
    def __init__(self):
        self.models = {'embeddinggemma': 2_000_000_000, 'llama3.2:3b': 6_000_000_000}
        self.loaded = {}
        self.actions = []
        self.fail = False

    def ps(self):
        if self.fail:
            raise OSError('offline')
        return [{'name': name, 'size': size, 'size_vram': size} for name, size in self.loaded.items()]

    def control(self, model, keep_alive, embed=False):
        self.actions.append((model, keep_alive, embed))
        if keep_alive == '0':
            self.loaded.pop(model, None)
        else:
            self.loaded[model] = self.models.get(model, 1_000_000_000)


class ResidencyTests(unittest.TestCase):
    def test_settings_switch_updates_the_residency_preload_model(self):
        from backend.models import AIConfigRequest
        from backend.routes import settings
        from ml.llm_service import LLMService
        transport = FakeTransport()
        controller = ResidencyController(transport=transport, clock=lambda: 0)
        service = LLMService()
        with patch.object(settings, 'residency', controller), patch.object(settings, 'llm_service', service):
            settings.set_ai_config(AIConfigRequest(model='replacement-model'))
        controller.transition('PAUSED')
        self.assertEqual(controller.llm, 'replacement-model')
        self.assertEqual(transport.actions[0][:2], ('replacement-model', '-1'))

    def test_no_player_does_not_preload_and_latest_alias_is_resident(self):
        transport = FakeTransport()
        controller = ResidencyController(transport=transport, clock=lambda: 0)
        controller.tick()
        self.assertEqual(transport.actions, [])
        transport.loaded = {'embeddinggemma:latest': 1000, 'llama3.2:3b': 2000}
        controller.transition('PAUSED')
        self.assertEqual(transport.actions, [('llama3.2:3b', '-1', False)])

    def test_pause_preload_play_dwell_and_hidden_release(self):
        tick = [0.0]
        transport = FakeTransport()
        transport.loaded = transport.models.copy()
        controller = ResidencyController(transport=transport, clock=lambda: tick[0])
        controller.budget_mb = 4000
        controller.transition('PLAYING')
        self.assertEqual(transport.actions[-1][:2], ('embeddinggemma', '-1'))
        tick[0] = controller.play_dwell - 0.1
        controller.tick()
        self.assertEqual(len(transport.actions), 1)
        tick[0] = controller.play_dwell + 0.1
        controller.tick()
        self.assertEqual(transport.actions[-1][:2], ('llama3.2:3b', '0'))
        controller.transition('PAUSED')
        self.assertEqual(len(transport.actions), 2)  # cooldown
        tick[0] += controller.cooldown + 0.1
        controller.tick()
        self.assertEqual(transport.actions[-1][:2], ('llama3.2:3b', '-1'))
        controller.transition('HIDDEN')
        tick[0] += controller.hidden_dwell + controller.cooldown + 0.1
        controller.tick()
        self.assertEqual(transport.actions[-1][:2], ('llama3.2:3b', '0'))

    def test_offline_falls_back_to_default_keep_alive(self):
        transport = FakeTransport()
        transport.fail = True
        controller = ResidencyController(transport=transport, clock=lambda: 0)
        self.assertFalse(controller.transition('PAUSED')['enabled'])
        self.assertEqual(controller.keep_alive(controller.llm), controller.default_keep_alive)
