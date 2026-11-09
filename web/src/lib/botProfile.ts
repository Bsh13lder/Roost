// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Milind Soni and OpenMausBot contributors
// Modified from OpenMausBot shared/bot-profile.ts @ 3b1f6de by BlckIt, 2026: fitsOnOneLine kept as is;
// BOT_PROFILE_LIMITS replaced by Roost's own limits (roost/constants.py).
// Licensed under the Apache License, Version 2.0 (the "License"); you may not use
// this file except in compliance with the License. You may obtain a copy of the
// License at http://www.apache.org/licenses/LICENSE-2.0 (also LICENSES/Apache-2.0.txt).
// Unless required by applicable law or agreed to in writing, software distributed
// under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
// CONDITIONS OF ANY KIND, either express or implied. See the License for the
// specific language governing permissions and limitations under the License.

// Roost's limits; the server enforces the same (roost/constants.py MAX_BOT_*).
export const BOT_LIMITS = { name: 40, job: 200, instructions: 4000, group: 30 } as const;
// The server's BOT_NAME_PATTERN, ^[\w][\w .\-]{0,39}$, with \w read as Unicode letters, digits and _.
export const NAME_PATTERN = /^[\p{L}\p{N}_][\p{L}\p{N}_ .-]{0,39}$/u;

/** A name or job is quoted as one line in prompts and cards; text that could
 * break out of that line is refused at the door. */
export function fitsOnOneLine(value: string): boolean {
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    if (code < 0x20 || (code >= 0x7f && code <= 0x9f) || code === 0x2028 || code === 0x2029) return false;
  }
  return true;
}
