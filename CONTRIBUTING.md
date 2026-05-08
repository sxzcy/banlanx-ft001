# Contributing

Keep changes focused on the BanlanX FT001 integration.

Before opening a pull request, run:

```bash
python -m compileall custom_components/banlanx_ft001
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/banlanx_ft001 -q
```

When changing protocol parsing or command payloads, add or update a test with a
fixed packet sample.
