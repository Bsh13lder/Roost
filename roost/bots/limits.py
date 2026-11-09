# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Milind Soni and OpenMausBot contributors
# Modified from OpenMausBot shared/bot-profile.ts @ 3b1f6de by BlckIt, 2026: fitsOnOneLine ported to Python
# as fits_on_one_line; the profile limits are Roost's own (roost/constants.py).
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. You may obtain a copy of the
# License at http://www.apache.org/licenses/LICENSE-2.0 (also LICENSES/Apache-2.0.txt).
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""A bot's name and job are quoted in prompts and cards as one line: a roster
entry, a "Created <name>" card. Text that could break out of that line is
refused at the door rather than flattened later: a newline, a control
character, or a Unicode line or paragraph separator. That way a model-written
job can't forge a roster line."""

from __future__ import annotations

_LINE_SEPARATORS = (0x2028, 0x2029)


def _breaks_line(code: int) -> bool:
    return code < 0x20 or 0x7F <= code <= 0x9F or code in _LINE_SEPARATORS


def fits_on_one_line(value: str) -> bool:
    return not any(_breaks_line(ord(char)) for char in value)
