__all__ = ["TOOLS", "TOOLS_SCHEMA", "call_tool", "render_tools_prompt"]


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(name)
    import importlib

    registry = importlib.import_module(".registry", __name__)
    return getattr(registry, name)
