"""Tests for SSE publisher."""

import asyncio

import pytest

from sse_publisher import SsePublisher


@pytest.mark.asyncio
async def test_publish_delivers_to_all_subscribers():
    pub = SsePublisher()
    q1 = pub.subscribe()
    q2 = pub.subscribe()
    await pub.publish("test_evt", {"x": 1})
    m1 = await asyncio.wait_for(q1.get(), timeout=2)
    m2 = await asyncio.wait_for(q2.get(), timeout=2)
    assert "event: test_evt" in m1
    assert '"x": 1' in m1
    assert m1 == m2


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    pub = SsePublisher()
    q = pub.subscribe()
    pub.unsubscribe(q)
    await pub.publish("gone", {})
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q.get(), timeout=0.2)


def test_subscriber_count():
    pub = SsePublisher()
    assert pub.subscriber_count == 0
    q = pub.subscribe()
    assert pub.subscriber_count == 1
    pub.unsubscribe(q)
    assert pub.subscriber_count == 0
