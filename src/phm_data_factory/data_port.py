"""Versioned, read-only benchmark facade over :class:`AgentDataTools`."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean
from typing import Any, Mapping, Sequence

from .agent import AgentDataTools
from .contract import (
    API_SCHEMA_VERSION,
    CAPABILITY_SCHEMA_VERSION,
    PACKAGE_VERSION,
)


_PUBLIC_SAMPLE_FIELDS = (
    "sample_id",
    "dataset_id",
    "name",
    "description",
    "type",
    "visible",
    "domain_id",
    "domain_description",
    "sample_rate",
    "sample_length",
    "channels",
    "fault_diagnosis",
    "anomaly_detection",
    "remaining_life",
    "digital_twin_prediction",
    "signal_available",
    "stored_shape",
)
_SEARCH_FIELDS = {"dataset_id", "name", "domain_id", "task"}
_TASK_FIELDS = {
    "fault": "fault_diagnosis",
    "fault_diagnosis": "fault_diagnosis",
    "anomaly": "anomaly_detection",
    "anomaly_detection": "anomaly_detection",
    "rul": "remaining_life",
    "remaining_life": "remaining_life",
    "digital_twin": "digital_twin_prediction",
    "digital_twin_prediction": "digital_twin_prediction",
}
_WINDOW_FIELDS = {"sample_id", "start", "end", "channels", "max_points"}
_STREAM_FIELDS = {"stream_id", "channels", "max_points", "watermark"}
_REGISTERED_STREAM_MEMBER_FIELDS = {
    "source_sample_id",
    "sample_id",
    "replay_step",
    "elapsed_minutes",
}


@dataclass(frozen=True)
class _RegisteredStreamMember:
    source_sample_id: str
    sample_id: str
    replay_step: int
    elapsed_minutes: int | float


def _freeze_registered_streams(
    registered_streams: Mapping[str, Sequence[Mapping[str, Any]]] | None,
) -> dict[str, tuple[_RegisteredStreamMember, ...]]:
    if registered_streams is None:
        return {}
    if not isinstance(registered_streams, Mapping):
        raise ValueError("registered_streams must be a mapping")

    frozen: dict[str, tuple[_RegisteredStreamMember, ...]] = {}
    public_ids: set[str] = set()
    source_ids: set[str] = set()
    for stream_id, raw_members in registered_streams.items():
        if not isinstance(stream_id, str) or not stream_id:
            raise ValueError("registered stream ids must be non-empty strings")
        if isinstance(raw_members, (str, bytes)) or not isinstance(
            raw_members, Sequence
        ):
            raise ValueError("registered stream members must be a sequence")
        if not raw_members:
            raise ValueError("registered streams must contain at least one member")

        members: list[_RegisteredStreamMember] = []
        previous_elapsed: float | None = None
        for index, raw_member in enumerate(raw_members):
            if not isinstance(raw_member, Mapping):
                raise ValueError("registered stream members must be mappings")
            if set(raw_member) != _REGISTERED_STREAM_MEMBER_FIELDS:
                raise ValueError(
                    "registered stream members must contain exactly "
                    f"{sorted(_REGISTERED_STREAM_MEMBER_FIELDS)}"
                )

            source_sample_id = raw_member["source_sample_id"]
            sample_id = raw_member["sample_id"]
            replay_step = raw_member["replay_step"]
            elapsed_minutes = raw_member["elapsed_minutes"]
            if not isinstance(source_sample_id, str) or not source_sample_id:
                raise ValueError("source_sample_id must be a non-empty string")
            if not isinstance(sample_id, str) or not sample_id:
                raise ValueError("sample_id must be a non-empty opaque string")
            if source_sample_id == sample_id:
                raise ValueError("sample_id must be opaque from source_sample_id")
            if sample_id in public_ids:
                raise ValueError("registered public sample ids must be unique")
            if (
                isinstance(replay_step, bool)
                or not isinstance(replay_step, int)
                or replay_step != index
            ):
                raise ValueError("replay_step must be zero-based and contiguous")
            if (
                isinstance(elapsed_minutes, bool)
                or not isinstance(elapsed_minutes, (int, float))
                or not math.isfinite(float(elapsed_minutes))
            ):
                raise ValueError("elapsed_minutes must be a finite number")
            elapsed_value = float(elapsed_minutes)
            if previous_elapsed is not None and elapsed_value <= previous_elapsed:
                raise ValueError("elapsed_minutes must be strictly increasing")

            public_ids.add(sample_id)
            source_ids.add(source_sample_id)
            previous_elapsed = elapsed_value
            members.append(
                _RegisteredStreamMember(
                    source_sample_id=source_sample_id,
                    sample_id=sample_id,
                    replay_step=replay_step,
                    elapsed_minutes=elapsed_minutes,
                )
            )
        frozen[stream_id] = tuple(members)

    if public_ids & source_ids:
        raise ValueError("public sample ids must not collide with raw source ids")
    return frozen


def _public_sample(row: Mapping[str, Any]) -> dict[str, Any]:
    """Project only the declared public metadata fields."""

    return {key: row[key] for key in _PUBLIC_SAMPLE_FIELDS if key in row}


def _backend_kind(tools: AgentDataTools) -> str:
    store_name = type(tools.repository.signals).__name__.lower()
    if "iotdb" in store_name:
        return "iotdb"
    if "h5" in store_name:
        return "local_hdf5"
    return "local"


def _channel_index(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("stream channels must be channel indices")
    text = str(value)
    if text.startswith("ch_"):
        text = text[3:]
    elif text.startswith("ch"):
        text = text[2:]
    try:
        channel = int(text)
    except (TypeError, ValueError):
        raise ValueError("stream channels must be channel indices") from None
    if channel < 0:
        raise ValueError("stream channels must be non-negative")
    return channel


def _stream_position(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("stream watermark must be a canonical integer position")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            position = int(value)
        except ValueError:
            pass
        else:
            if str(position) == value:
                return position
    raise ValueError("stream watermark must be a canonical integer position")


class StreamCursor:
    """Read contiguous bounded windows without exposing future samples."""

    def __init__(
        self,
        port: "AgentDataPort",
        *,
        stream_id: str,
        channels: tuple[int, ...],
        max_points: int,
        position: int,
        length: int,
        members: tuple[_RegisteredStreamMember, ...] | None = None,
    ) -> None:
        self._port = port
        self._stream_id = stream_id
        self._channels = channels
        self._max_points = max_points
        self._position = position
        self._length = length
        self._members = members
        self._closed = False

    @property
    def cursor_id(self) -> str:
        return f"stream://{self._port.backend_kind}/{self._stream_id}"

    @property
    def position(self) -> str:
        return str(self._position)

    @property
    def backend_kind(self) -> str:
        return self._port.backend_kind

    @property
    def resumable(self) -> bool:
        return True

    @property
    def exhausted(self) -> bool:
        return self._position >= self._length

    def next(self) -> dict[str, Any] | None:
        """Release the next contiguous window and advance the public watermark."""

        if self._closed:
            raise ValueError("stream cursor is closed")
        if self.exhausted:
            return None
        if self._members is not None:
            member = self._members[self._position]
            artifact = self._port._read_registered_member(
                member,
                channels=self._channels,
                max_points=self._max_points,
            )
            previous_elapsed = (
                member.elapsed_minutes
                if member.replay_step == 0
                else self._members[self._position - 1].elapsed_minutes
            )
            elapsed_delta = member.elapsed_minutes - previous_elapsed
            self._port._release_registered_member(self._stream_id, member)
            self._position += 1
            return {
                **artifact,
                "stream_id": self._stream_id,
                "replay_step": member.replay_step,
                "elapsed_minutes": member.elapsed_minutes,
                "elapsed_delta_minutes": elapsed_delta,
                "cursor_id": self.cursor_id,
                "position": self.position,
                "exhausted": self.exhausted,
            }

        start = self._position
        end = min(start + self._max_points, self._length)
        artifact = self._port.read_window(
            {
                "sample_id": self._stream_id,
                "start": start,
                "end": end,
                "channels": self._channels,
                "max_points": self._max_points,
            }
        )
        self._position = end
        return {
            **artifact,
            "cursor_id": self.cursor_id,
            "position": self.position,
            "exhausted": self.exhausted,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "cursor_id": self.cursor_id,
            "position": self.position,
            "backend_kind": self.backend_kind,
            "resumable": self.resumable,
        }

    def close(self) -> None:
        self._closed = True
        self._port._discard_cursor(self)

    def _close_from_port(self) -> None:
        self._closed = True

    def __enter__(self) -> "StreamCursor":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


class AgentDataPort:
    """Expose the stable six-method benchmark data contract.

    The wrapped ``AgentDataTools`` remains unchanged for v0.2 consumers. This
    facade narrows metadata to a public projection and keeps window artifacts
    session-local, so a summary can refer only to a window actually read in
    this port session.
    """

    def __init__(
        self,
        tools: AgentDataTools,
        registered_streams: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> None:
        self._tools = tools
        self._backend_kind = _backend_kind(tools)
        self._registered_streams = _freeze_registered_streams(registered_streams)
        self._public_members = {
            member.sample_id: member
            for members in self._registered_streams.values()
            for member in members
        }
        self._source_members: dict[str, list[_RegisteredStreamMember]] = {}
        for member in self._public_members.values():
            self._source_members.setdefault(member.source_sample_id, []).append(member)
        self._released_public_ids: set[str] = set()
        self._released_stream_positions = {
            stream_id: 0 for stream_id in self._registered_streams
        }
        self._artifacts: dict[str, dict[str, Any]] = {}
        self._next_artifact = 1
        self._cursors: set[StreamCursor] = set()

    @property
    def backend_kind(self) -> str:
        return self._backend_kind

    def manifest(self) -> dict[str, Any]:
        return {
            "provider": "phm-data-factory",
            "package_version": PACKAGE_VERSION,
            "api_schema_version": API_SCHEMA_VERSION,
            "capability_schema_version": CAPABILITY_SCHEMA_VERSION,
            "backend_kind": self._backend_kind,
            "read_only": True,
            "capabilities": {
                "search_samples": True,
                "describe_sample": True,
                "bounded_window": True,
                "window_statistics": True,
                "stream_cursor": True,
                "modalities": ["continuous_series"],
                "timestamp_bases": ["sample_index"],
                "label_visibility_policy": "public_evaluator_private_v1",
            },
        }

    def search_samples(
        self, query: Mapping[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        if not isinstance(query, Mapping):
            raise ValueError("query must be a mapping")
        unknown = set(query) - _SEARCH_FIELDS
        if unknown:
            raise ValueError(f"unsupported public search fields: {sorted(unknown)}")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        if self._registered_streams:
            released_source_ids = [
                member.source_sample_id
                for sample_id, member in self._public_members.items()
                if sample_id in self._released_public_ids
            ]
            if not released_source_ids:
                return []
            filters = {
                field: query[field]
                for field in ("dataset_id", "name", "domain_id")
                if query.get(field) is not None
            }
            task = query.get("task")
            if task:
                try:
                    filters[_TASK_FIELDS[task.lower()]] = True
                except (AttributeError, KeyError):
                    raise ValueError(f"Unknown task: {task}") from None
            filters["sample_id"] = released_source_ids
            rows = self._tools.repository.search_samples(
                filters, limit=None, visible_only=True
            )
            public_rows = []
            for row in rows:
                for member in self._source_members.get(str(row.get("sample_id")), ()):
                    if member.sample_id not in self._released_public_ids:
                        continue
                    public = _public_sample(row)
                    public["sample_id"] = member.sample_id
                    public_rows.append(public)
                    if len(public_rows) == limit:
                        return public_rows
            return public_rows
        rows = self._tools.search_samples(
            dataset_id=query.get("dataset_id"),
            name=query.get("name"),
            domain_id=query.get("domain_id"),
            task=query.get("task"),
            visible_only=True,
            limit=limit,
        )
        return [_public_sample(row) for row in rows[:limit]]

    def describe_sample(self, sample_id: str) -> dict[str, Any]:
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError("sample_id must be a non-empty string")
        source_sample_id = self._resolve_public_sample_id(sample_id)
        public = _public_sample(self._tools.get_sample_metadata(source_sample_id))
        if self._registered_streams:
            public["sample_id"] = sample_id
        return public

    def read_window(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            raise ValueError("window request must be a mapping")
        unknown = set(request) - _WINDOW_FIELDS
        if unknown:
            raise ValueError(f"unsupported window fields: {sorted(unknown)}")
        sample_id = request.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError("sample_id must be a non-empty string")
        source_sample_id = self._resolve_public_sample_id(sample_id)
        start = request.get("start", 0)
        end = request.get("end")
        max_points = request.get("max_points", self._tools.default_max_points)
        if isinstance(start, bool) or not isinstance(start, int) or start < 0:
            raise ValueError("window start must be a non-negative integer")
        if isinstance(end, bool) or not isinstance(end, int) or end <= start:
            raise ValueError("window end must be an increasing integer")
        if (
            isinstance(max_points, bool)
            or not isinstance(max_points, int)
            or max_points <= 0
        ):
            raise ValueError("max_points must be a positive integer")
        if end - start > max_points:
            raise ValueError("exact window exceeds max_points")
        raw_channels = request.get("channels")
        if raw_channels is not None and (
            isinstance(raw_channels, (str, bytes))
            or not isinstance(raw_channels, Sequence)
        ):
            raise ValueError("channels must be a sequence of indices")
        channels = None
        if raw_channels is not None:
            channels = [_channel_index(value) for value in raw_channels]
        if channels is not None and (
            not channels or len(set(channels)) != len(channels)
        ):
            raise ValueError("channels must be non-empty and unique")

        return self._read_exact_window(
            source_sample_id=source_sample_id,
            public_sample_id=sample_id,
            start=start,
            end=end,
            channels=None if channels is None else tuple(channels),
            max_points=max_points,
        )

    def _read_exact_window(
        self,
        *,
        source_sample_id: str,
        public_sample_id: str,
        start: int,
        end: int,
        channels: tuple[int, ...] | None,
        max_points: int,
    ) -> dict[str, Any]:
        raw = self._tools.get_signal_window(
            source_sample_id,
            start=start,
            end=end,
            channels=channels,
            max_points=max_points,
        )
        if raw.get("start") != start or raw.get("end") != end or raw.get("step") != 1:
            raise ValueError("provider did not return the exact requested window")
        returned_channels = raw.get("channels")
        if not isinstance(returned_channels, list) or not returned_channels:
            raise ValueError("provider did not return the exact requested window")
        if channels is not None and returned_channels != list(channels):
            raise ValueError("provider did not return the exact requested window")
        expected_shape = [end - start, len(returned_channels)]
        if raw.get("shape") != expected_shape:
            raise ValueError("provider did not return the exact requested window")
        values = raw.get("values")
        if not isinstance(values, list) or len(values) != expected_shape[0]:
            raise ValueError("provider did not return the exact requested window")
        if any(
            not isinstance(row, list) or len(row) != expected_shape[1]
            for row in values
        ):
            raise ValueError("provider did not return the exact requested window")
        artifact_ref = f"artifact://window/{self._next_artifact:06d}"
        self._next_artifact += 1
        artifact = dict(raw)
        artifact["sample_id"] = public_sample_id
        artifact.update(
            artifact_ref=artifact_ref,
            kind="continuous_series",
            modality="continuous_series",
        )
        self._artifacts[artifact_ref] = artifact
        return dict(artifact)

    def _resolve_public_sample_id(self, sample_id: str) -> str:
        if not self._registered_streams:
            return sample_id
        if sample_id in self._source_members:
            raise ValueError("raw source sample ids are not accepted")
        try:
            member = self._public_members[sample_id]
        except KeyError:
            raise ValueError("unknown public sample id") from None
        if sample_id not in self._released_public_ids:
            raise ValueError("public sample is not yet released")
        return member.source_sample_id

    def _read_registered_member(
        self,
        member: _RegisteredStreamMember,
        *,
        channels: tuple[int, ...],
        max_points: int,
    ) -> dict[str, Any]:
        description = self._tools.repository.get_sample_metadata(
            member.source_sample_id
        )
        shape = description.get("stored_shape")
        if not isinstance(shape, list) or not shape:
            raise ValueError("registered stream member has no readable signal shape")
        length = int(shape[0])
        if length <= 0:
            raise ValueError("registered stream member has no signal points")
        if length > max_points:
            raise ValueError("registered stream member exceeds max_points")
        channel_count = 1 if len(shape) == 1 else int(shape[1])
        selected_channels = channels or tuple(range(channel_count))
        if any(channel >= channel_count for channel in selected_channels):
            raise ValueError("stream channel is outside the sample")
        return self._read_exact_window(
            source_sample_id=member.source_sample_id,
            public_sample_id=member.sample_id,
            start=0,
            end=length,
            channels=selected_channels,
            max_points=max_points,
        )

    def _release_registered_member(
        self, stream_id: str, member: _RegisteredStreamMember
    ) -> None:
        released_position = self._released_stream_positions[stream_id]
        if member.replay_step > released_position:
            raise ValueError("registered stream release would skip a future sample")
        self._released_public_ids.add(member.sample_id)
        if member.replay_step == released_position:
            self._released_stream_positions[stream_id] = released_position + 1

    def summarize_window(self, artifact_ref: str) -> dict[str, Any]:
        if not isinstance(artifact_ref, str) or not artifact_ref:
            raise ValueError("artifact_ref must be a non-empty string")
        try:
            artifact = self._artifacts[artifact_ref]
        except KeyError:
            raise KeyError("unknown window artifact") from None
        rows = artifact["values"]
        if not rows:
            raise ValueError("cannot summarize an empty window")
        matrix = [row if isinstance(row, list) else [row] for row in rows]
        channel_count = len(matrix[0])
        if channel_count == 0 or any(len(row) != channel_count for row in matrix):
            raise ValueError("window values must be a regular matrix")
        channels = artifact["channels"]
        summaries = []
        for index in range(channel_count):
            values = [float(row[index]) for row in matrix]
            if not all(math.isfinite(value) for value in values):
                raise ValueError("window values must be finite")
            mean = fmean(values)
            summaries.append(
                {
                    "channel": channels[index],
                    "count": len(values),
                    "mean": mean,
                    "standard_deviation": math.sqrt(
                        fmean((value - mean) ** 2 for value in values)
                    ),
                    "rms": math.sqrt(fmean(value * value for value in values)),
                    "peak_to_peak": max(values) - min(values),
                }
            )
        return {
            "artifact_ref": artifact_ref,
            "sample_count": len(matrix),
            "channels": summaries,
        }

    def open_stream(self, request: Mapping[str, Any]) -> StreamCursor:
        if not isinstance(request, Mapping):
            raise ValueError("stream request must be a mapping")
        unknown = set(request) - _STREAM_FIELDS
        if unknown:
            raise ValueError(f"unsupported stream fields: {sorted(unknown)}")
        stream_id = request.get("stream_id")
        if not isinstance(stream_id, str) or not stream_id:
            raise ValueError("stream_id must be a non-empty sample id")
        max_points = request.get("max_points", self._tools.default_max_points)
        if (
            isinstance(max_points, bool)
            or not isinstance(max_points, int)
            or max_points <= 0
        ):
            raise ValueError("max_points must be a positive integer")
        watermark = request.get("watermark")
        start = 0 if watermark is None else _stream_position(watermark)
        raw_channels = request.get("channels", ())
        if isinstance(raw_channels, (str, bytes)) or not isinstance(
            raw_channels, Sequence
        ):
            raise ValueError("stream channels must be a sequence")
        channels = tuple(_channel_index(value) for value in raw_channels)
        if len(set(channels)) != len(channels):
            raise ValueError("stream channels must be unique")

        if self._registered_streams:
            if stream_id in self._source_members:
                raise ValueError("raw source sample ids are not accepted")
            try:
                members = self._registered_streams[stream_id]
            except KeyError:
                raise ValueError("unknown registered stream id") from None
            if start < 0 or start > len(members):
                raise ValueError("stream watermark is outside the registered stream")
            if start > self._released_stream_positions[stream_id]:
                raise ValueError("stream watermark is ahead of the released position")
            cursor = StreamCursor(
                self,
                stream_id=stream_id,
                channels=channels,
                max_points=max_points,
                position=start,
                length=len(members),
                members=members,
            )
            self._cursors.add(cursor)
            return cursor

        description = self.describe_sample(stream_id)
        shape = description.get("stored_shape")
        if not isinstance(shape, list) or not shape:
            raise ValueError("sample has no readable signal shape")
        length = int(shape[0])
        if start < 0 or start > length:
            raise ValueError("stream watermark is outside the sample")
        channel_count = 1 if len(shape) == 1 else int(shape[1])
        if not channels:
            channels = tuple(range(channel_count))
        if any(channel >= channel_count for channel in channels):
            raise ValueError("stream channel is outside the sample")
        cursor = StreamCursor(
            self,
            stream_id=stream_id,
            channels=channels,
            max_points=max_points,
            position=start,
            length=length,
        )
        self._cursors.add(cursor)
        return cursor

    def _discard_cursor(self, cursor: StreamCursor) -> None:
        self._cursors.discard(cursor)

    def close(self) -> None:
        for cursor in tuple(self._cursors):
            cursor._close_from_port()
        self._cursors.clear()
        self._artifacts.clear()
        self._tools.close()

    def __enter__(self) -> "AgentDataPort":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
