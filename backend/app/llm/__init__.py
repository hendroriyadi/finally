"""The project's only model-facing code.

Everything that talks to an LLM — or stands in for one — lives in this
package. `client.py` holds the real, network-bound LiteLLM/OpenRouter/
Cerebras call; `mock.py` holds a pure, deterministic stand-in used when
`LLM_MOCK=true`. Both expose the same return type, `ChatCompletionResult`
(defined in `schemas.py`), on purpose: nothing above this package — not
`app/routes/chat.py`, not any test — is permitted to branch on which of the
two actually ran. The dispatcher in `app/routes/chat.py` is the only code
that knows both exist.
"""

from __future__ import annotations
