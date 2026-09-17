import threading

from app.ui_dispatch import UiEventBridge


def test_ui_event_bridge_moves_worker_updates_to_ui_thread():
    bridge = UiEventBridge()
    received = []

    worker = threading.Thread(
        target=lambda: bridge.post(lambda: received.append("download complete")),
    )
    worker.start()
    worker.join()

    assert received == []
    assert bridge.drain() == 1
    assert received == ["download complete"]
