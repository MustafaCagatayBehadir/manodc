"""Background workers for the ManoDC module."""
import logging
import select
import socket
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Union

import _ncs
import ncs
from _ncs import events


def notif_reader(_queue):
    """Read notifications from NSO API and put on q"""
    log = logging.getLogger("notif_reader")
    log.info("notif_reader started")
    q_putter(get_cq_progress_notification(), _queue, 200000)


def get_cq_progress_notification():
    """Read CQ progress notifications from NSO API and put on q"""

    def retime() -> str:
        """Return the current time in ISO format"""
        now_utc = datetime.now(timezone.utc)
        now_utc_plus_3 = now_utc + timedelta(hours=3)
        return now_utc_plus_3.strftime("%Y-%m-%d %H:%M:%S")

    def normalize_event(cq_pev):
        """Normalize the event to a common format"""
        cq_pev["timestamp"] = retime()
        # Remove keys with list values containing _ncs.Value instances
        cq_pev = {
            k: v
            for k, v in cq_pev.items() if not (isinstance(v, list) and any(isinstance(_, _ncs.Value) for _ in v))
        }
        return cq_pev

    log = logging.getLogger("get_cq_progress_notification")
    event_sock = socket.socket()
    mask = events.NCS_NOTIF_CQ_PROGRESS
    noexists = _ncs.Value(init=1, type=_ncs.C_NOEXISTS)
    notif_data = events.NotificationsData(
        heartbeat_interval=1000,
        health_check_interval=1000,
        stream_name="ncs-events",
        start_time=noexists,
        stop_time=noexists,
        verbosity=ncs.VERBOSITY_VERY_VERBOSE,
    )
    events.notifications_connect2(event_sock, mask, ip="127.0.0.1", port=ncs.NCS_PORT, data=notif_data)

    while True:
        (readables, _, _) = select.select([event_sock], [], [], 0.1)
        for readable in readables:
            if readable == event_sock:
                event_dict = events.read_notification(event_sock)
                if event_dict["type"] != events.NCS_NOTIF_CQ_PROGRESS:
                    raise ValueError(f"Unhandled event type: {event_dict['type']}")

                cq_pev = event_dict["cq_progress"]

                if "trace_id" not in cq_pev:
                    log.debug("Skipping event without trace-id")
                    continue

                cq_pev = normalize_event(cq_pev)
                yield cq_pev

        if readables == []:
            # we feed dummy events if there are no real events, this is so
            # that the downstream consumer of events is always "woken up"
            # with the arrival of a new event, at least every 0.1 seconds
            yield None


def plan_handler(_queue):
    """A fault-tolerant wrapper of the main processing pipeline

    Catch any encountered exceptions, log em and restart the pipeline. Sleeps
    for a little while to avoid busy-dying.
    """
    log = logging.getLogger("plan_handler")
    log.info("plan_handler started")
    while True:
        try:
            plan_executor(_queue)
        except Exception:  # pylint:disable=broad-except
            log.error("Unhandled exception, will restart after short sleep...")
            log.error(traceback.format_exc())
            time.sleep(1)


def get_parse_csv_action_data(trans: ncs.maapi.Transaction, trace_id: str) -> Union[ncs.maagic.ListElement, None]:
    """Get the parse-csv action data with the commit trace_id."""
    action_data = []

    def helper_function(kp, _):
        action_data.append(ncs.maagic.get_node(trans, kp.dup()))

    expr = f"/manodc-actions/parse-csv-data[trace-id='{trace_id}']"
    trans.xpath_eval(expr, helper_function, trace=None, path="")
    return action_data[0] if action_data else None


def is_cq_completed(action_data: ncs.maagic.ListElement) -> bool:
    """Check if the CQ is completed."""
    for component in action_data.plan.component:
        if component.name == "self":
            continue
        if any(state.status not in ("reached", "failed") for state in component.state):
            return False
    return True


def handle_component_states(action_data: ncs.maagic.ListElement, switch: str, status: str) -> None:
    """Handle component states by setting the status."""
    sw_component = action_data.plan.component[switch]
    for state in (s for s in sw_component.state if s.status != "failed"):
        state.status = status

    self_component = action_data.plan.component["self"]
    if status == "failed":
        for _state in ["manodc:configured", "ncs:ready"]:
            self_component.state[_state].status = "failed"
    elif is_cq_completed(action_data):
        for _state in ["manodc:configured", "ncs:ready"]:
            if self_component.state[_state].status != "failed":
                self_component.state[_state].status = "reached"


def plan_executor(_queue):
    """Reads cq events from a queue and processes them.
    This is the main processing pipeline. It reads events from a queue and
    processes them. The processing is done in a fault-tolerant manner.
    """

    log = logging.getLogger("plan_executor")
    stream = q_getter(_queue)

    for event in stream:
        if not event:
            continue
        log.debug("Processing event: %s", event)
        with ncs.maapi.single_write_trans("admin", "system", db=ncs.OPERATIONAL) as trans:
            action_data = get_parse_csv_action_data(trans, event["trace_id"])
            if action_data is None:
                log.warning("No action data found for trace ID %s", event["trace_id"])
                continue

            completed_devices = event.get("completed_devices", [])
            failed_devices = event.get("failed_devices", [])

            for switch in completed_devices:
                handle_component_states(action_data, switch, "reached")
            for switch in failed_devices:
                handle_component_states(action_data, switch, "failed")

            if completed_devices or failed_devices:
                trans.apply()


def q_putter(stream, _queue, qlimit):
    """Reads events from a stream and places them on a queue

    If there are more than qlimit number of items already in the queue, we drop
    the event. We log but are rather careful not to log to often since that
    could have a detrimental effect on performance.
    """
    log = logging.getLogger("q_putter")

    dropped = 0
    last = time.time()
    for event in stream:
        if _queue.qsize() <= qlimit:
            _queue.put(event)
        else:
            dropped += 1

        if dropped > 0 and time.time() > last + 1:
            log.debug("Dropped %s events due to full queue", dropped)
            last = time.time()
            dropped = 0


def q_getter(_queue):
    """Read events from a queue and yield as a generator

    Works well together with q_putter!
    """
    while True:
        yield _queue.get()
