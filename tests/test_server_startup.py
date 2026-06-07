from __future__ import annotations

import serve


def test_dev_server_disables_reloader_for_playwright(monkeypatch):
    run_kwargs = {}

    def fake_run(*_args, **kwargs):
        run_kwargs.update(kwargs)

    monkeypatch.setattr(serve, 'init_db', lambda: None)
    monkeypatch.setattr(serve.app, 'run', fake_run)

    serve.main()

    assert run_kwargs['debug'] is True
    assert run_kwargs['port'] == 5000
    assert run_kwargs['use_reloader'] is False
