"""The client catalog never infers free access from a cloud provider label."""
from pathlib import Path
from tempfile import TemporaryDirectory
from ailinux_client.core.model_sync import ModelSyncManager


class Catalog:
    def get_models(self):
        return {
            'tier': 'registered',
            'models': ['nvidia/google/gemma-4-31b-it', 'ollama/qwen3.5:cloud', 'ollama/qwen3:8b'],
            'model_details': [
                {'id': 'nvidia/google/gemma-4-31b-it', 'provider': 'nvidia',
                 'free_endpoint': True, 'free_status': 'unknown', 'free_badge': False},
                {'id': 'ollama/qwen3.5:cloud', 'free_badge': False},
                {'id': 'ollama/qwen3:8b', 'free_badge': True},
                {'id': 'unlisted/paid', 'free_badge': True},
            ],
        }


def test_sync_uses_tier_scoped_model_details():
    with TemporaryDirectory() as tmp:
        folder = Path(tmp)
        manager = ModelSyncManager(config_dir=folder, api_client=Catalog())
        assert manager.sync(force=True)
        models = {m.id: m for m in manager.models}
        assert len(models) == 3
        assert models['nvidia/google/gemma-4-31b-it'].free_endpoint
        assert not models['nvidia/google/gemma-4-31b-it'].free
        assert models['ollama/qwen3.5:cloud'].category != 'local'
        assert models['ollama/qwen3:8b'].category == 'local'
        assert models['ollama/qwen3:8b'].free
        reopened = ModelSyncManager(config_dir=folder)
        assert len(reopened.models) == 3
