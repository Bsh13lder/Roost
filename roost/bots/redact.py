# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Milind Soni and OpenMausBot contributors
# Modified from OpenMausBot shared/redact.ts @ 3b1f6de by BlckIt, 2026: the content-shaped secret patterns
# ported to Python regexes and used to FIND secrets (Share as Template refuses), not to mask them; the
# held-secret scrubbers are not ported.
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. You may obtain a copy of the
# License at http://www.apache.org/licenses/LICENSE-2.0 (also LICENSES/Apache-2.0.txt).
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""Text that looks like a credential. High precision on purpose: only shapes
that are unmistakably keys, tokens or passwords match, so ordinary
instructions ("password: leave blank") never do."""

from __future__ import annotations

import re

_KEY_PREFIXES = tuple(re.compile(pattern) for pattern in (
    r"\bom[dg]_[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])",
    r"\bsk-(?:ant-|proj-|live-|test-)?[A-Za-z0-9_-]{16,}",
    r"\bxai-[A-Za-z0-9_-]{20,}",
    r"\bgsk_[A-Za-z0-9]{40,}",
    r"\bcsk-[A-Za-z0-9]{32,}",
    r"\bLLM\|\d{6,}\|[A-Za-z0-9_-]{16,}",
    r"\bhf_[A-Za-z0-9]{30,}",
    r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}",
    r"\bgithub_pat_[A-Za-z0-9_]{20,}",
    r"\bxox[abposr]-[A-Za-z0-9-]{20,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bAIza[0-9A-Za-z_-]{30,}",
    r"\bnpm_[A-Za-z0-9]{20,}",
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
))
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")
_KEY_VALUE = re.compile(
    r"\b(?:[A-Za-z0-9_-]*_)?(?:api[_-]?key|apikey|secret|token|password|passwd|authorization|auth[_-]?token|"
    r"access[_-]?key|private[_-]?key)s?[\"']?\s*[=:]\s*([\"']?)[A-Za-z0-9._~+/=-]{8,}\1", re.IGNORECASE)
_KEY_SUFFIX = re.compile(r"\b[A-Za-z][A-Za-z0-9_-]*[_-]key(?:s)?=([\"']?)[A-Za-z0-9._~+/=-]+\1", re.IGNORECASE)
_SECRET_FLAG = re.compile(
    r"--(?:token|password|passwd|api-key|apikey|secret|access-key|auth-token)(?:=|\s+)([\"']?)(?!-)"
    r"[A-Za-z0-9._~+/=-]+\1", re.IGNORECASE)
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_URL_USERINFO = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@'\"]+:[^\s/@'\"«»]+@", re.IGNORECASE)

_KINDS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    ("an API key or token", (*_KEY_PREFIXES, _BEARER, _KEY_VALUE, _KEY_SUFFIX, _SECRET_FLAG)),
    ("a private key", (_PEM,)),
    ("a password in a link", (_URL_USERINFO,)),
)


def find_secret_kinds(text: str) -> tuple[str, ...]:
    """The kinds of secret ``text`` seems to hold, in a fixed order; empty when none."""
    return tuple(kind for kind, patterns in _KINDS if any(p.search(text) for p in patterns))
