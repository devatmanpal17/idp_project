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
    def test_switched_away_request_that_finishes_late_is_retired_again(self):
        now = [0.0]
        transport = FakeTransport()
        controller = ResidencyController(transport=transport, clock=lambda: now[0])
        controller.player_active = True
        previous = controller.llm
        keep_alive = controller.keep_alive(previous)
        controller.set_chat_model('replacement-model')
        controller.tick()  # The old request is still loading, so /api/ps omits it.
        transport.loaded[previous] = 1000
        controller.request_completed(previous, keep_alive)
        now[0] += controller.cooldown + 1
        controller.tick()
        self.assertNotIn(previous, transport.loaded)

    def test_model_switch_retires_a_request_pin_before_the_next_controller_tick(self):
        transport = FakeTransport()
        controller = ResidencyController(transport=transport, clock=lambda: 0)
        controller.player_active = True
        previous = controller.llm
        self.assertEqual(controller.keep_alive(previous), -1)
        # The chat request loads/pins the model before the worker samples /api/ps.
        transport.loaded[previous] = 1000
        controller.set_chat_model('replacement-model')
        controller.tick()
        self.assertNotIn(previous, transport.loaded)

    def test_keep_alive_treats_implicit_latest_as_the_same_chat_model(self):
        controller = ResidencyController(transport=FakeTransport(), clock=lambda: 100)
        controller.player_active = True
        controller.llm = 'chat'
        controller.state = 'PLAYING'
        controller.state_since = 0
        self.assertEqual(controller.keep_alive('chat:latest'), controller.default_keep_alive)

    def test_model_switch_retires_only_the_previous_managed_chat_pin(self):
        from backend.routes import settings
        from backend.models import AIConfigRequest
        from ml.llm_service import LLMService
        now = [0.0]
        transport = FakeTransport()
        controller = ResidencyController(transport=transport, clock=lambda: now[0])
        controller.transition('PAUSED')
        previous = controller.llm
        self.assertIn(previous, transport.loaded)
        transport.loaded['external-model'] = 1000
        with patch.object(settings, 'residency', controller), \
             patch.object(settings, 'llm_service', LLMService()):
            settings.set_ai_config(AIConfigRequest(model='replacement-model'))
        now[0] += controller.cooldown + 1
        controller.tick()
        self.assertNotIn(previous, transport.loaded)
        self.assertIn('external-model', transport.loaded)

    def test_unmanaged_or_retired_model_requests_do_not_pin_forever(self):
        controller = ResidencyController(transport=FakeTransport(), clock=lambda: 0)
        controller.player_active = True
        self.assertEqual(controller.keep_alive('retired-chat'), controller.default_keep_alive)

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
