from __future__ import annotations

from dataclasses import dataclass

from keyrhythm.config import CHART_SAMPLE_RATE


@dataclass(slots=True)
class AudioTimeline:
    sample_rate: int = CHART_SAMPLE_RATE
    generation: int = 0
    chart_origin_frame: int = 0
    rendered_frame: int = 0
    output_latency_frames: int = 0
    stream_origin_ns: int | None = None
    stream_origin_chart_frame: int = 0

    def begin(self, start_frame: int, host_time_ns: int, output_latency_seconds: float) -> None:
        self.generation += 1
        self.chart_origin_frame = start_frame
        self.rendered_frame = start_frame
        self.stream_origin_chart_frame = start_frame
        self.stream_origin_ns = host_time_ns
        self.output_latency_frames = round(output_latency_seconds * self.sample_rate)

    def advance_rendered(self, frames: int) -> None:
        self.rendered_frame += frames

    def map_host_time(self, host_time_ns: int) -> int:
        if self.stream_origin_ns is None:
            return self.chart_origin_frame
        elapsed = host_time_ns - self.stream_origin_ns
        return self.stream_origin_chart_frame + round(elapsed * self.sample_rate / 1_000_000_000)

    def presented_frame(self, current_host_time_ns: int) -> int:
        return max(self.chart_origin_frame, self.map_host_time(current_host_time_ns) - self.output_latency_frames)

    def seek(self, frame: int, host_time_ns: int) -> None:
        self.generation += 1
        self.chart_origin_frame = frame
        self.rendered_frame = frame
        self.stream_origin_chart_frame = frame
        self.stream_origin_ns = host_time_ns

