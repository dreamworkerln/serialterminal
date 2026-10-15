from __future__ import annotations

from bisect import bisect_right
from collections.abc import MutableMapping


DEFAULT_MAX_RECEIVED_RANGES = 65_536
DEFAULT_MAX_MANIFEST_BYTES = 4 * 1024 * 1024


class ReceivedRanges(MutableMapping):
    """Карта полученных chunks с памятью пропорционально числу интервалов."""

    def __init__(self, meta, *, maximum=DEFAULT_MAX_RECEIVED_RANGES):
        self.meta = meta
        self.maximum = maximum
        self.starts = []
        self.ends = []
        self.count = 0

    def __len__(self):
        return self.count

    def __iter__(self):
        for start, end in zip(self.starts, self.ends):
            yield from range(start, end)

    def __contains__(self, index):
        position = bisect_right(self.starts, index) - 1
        return position >= 0 and index < self.ends[position]

    def __getitem__(self, index):
        if index not in self:
            raise KeyError(index)
        return min(self.meta.chunk_size, self.meta.wire_size - index * self.meta.chunk_size)

    def check_insert(self, index):
        position = bisect_right(self.starts, index)
        if position and index < self.ends[position - 1]:
            return
        left = position > 0 and self.ends[position - 1] == index
        right = position < len(self.starts) and self.starts[position] == index + 1
        if len(self.starts) + 1 - left - right > self.maximum:
            raise ValueError('received range limit exceeded')

    def __setitem__(self, index, length):
        expected = min(self.meta.chunk_size, self.meta.wire_size - index * self.meta.chunk_size)
        if type(index) is not int or index < 0 or expected <= 0 or length != expected:
            raise ValueError('invalid received chunk')
        self.check_insert(index)
        position = bisect_right(self.starts, index)
        if position and index < self.ends[position - 1]:
            return
        left = position > 0 and self.ends[position - 1] == index
        right = position < len(self.starts) and self.starts[position] == index + 1
        if left and right:
            self.ends[position - 1] = self.ends.pop(position)
            self.starts.pop(position)
        elif left:
            self.ends[position - 1] = index + 1
        elif right:
            self.starts[position] = index
        else:
            self.starts.insert(position, index)
            self.ends.insert(position, index + 1)
        self.count += 1

    def __delitem__(self, index):
        raise TypeError('received chunks cannot be removed from a live map')

    @property
    def byte_count(self):
        total = self.count * self.meta.chunk_size
        last = (self.meta.wire_size - 1) // self.meta.chunk_size
        if self.meta.wire_size and last in self:
            total -= self.meta.chunk_size - (self.meta.wire_size - last * self.meta.chunk_size)
        return total

    def ranges(self):
        return [[start, end - start] for start, end in zip(self.starts, self.ends)]

    def missing(self, count):
        cursor = 0
        for start, end in zip(self.starts, self.ends):
            if cursor < start:
                yield cursor, start - cursor
            cursor = end
        if cursor < count:
            yield cursor, count - cursor

    @classmethod
    def restore(cls, meta, count, ranges, *, maximum=DEFAULT_MAX_RECEIVED_RANGES):
        if not isinstance(ranges, list) or len(ranges) > maximum:
            return None
        result = cls(meta, maximum=maximum)
        previous = 0
        for pair in ranges:
            if not isinstance(pair, list) or len(pair) != 2 or any(type(value) is not int for value in pair):
                return None
            start, length = pair
            end = start + length
            if start < previous or start < 0 or length <= 0 or end > count:
                return None
            if result.ends and start == previous:
                result.ends[-1] = end
            else:
                result.starts.append(start)
                result.ends.append(end)
            result.count += length
            previous = end
        return result
