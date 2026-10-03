"""Jobs-profile-only plugin entry point. Install as a symlink to this directory."""
import importlib.util
from pathlib import Path


def register(ctx):
    from hermes_constants import get_hermes_home
    home = Path(get_hermes_home()).resolve()
    if home.name != 'jobs' or home.parent.name != 'profiles':
        raise RuntimeError('junter-actions is restricted to the jobs profile')
    module_path = Path(__file__).resolve().parents[1] / 'telegram_actions.py'
    spec = importlib.util.spec_from_file_location('junter_telegram_actions', module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError('junter integration source unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctx.register_hook('pre_gateway_dispatch', module.GatewayHook(home))
