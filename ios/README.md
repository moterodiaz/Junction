# MetaLab iOS client

Thin client for the Ray-Ban Display glasses. It captures one frame and one short command, sends a single `invoke` message, then shows the card and speaks the answer. It does not call a model.

The wire format is defined in [`contracts/ws-messages.schema.json`](../contracts/ws-messages.schema.json); the client's types are in `MetaLabCore/Sources/MetaLabCore/Contract.swift`.

## Gemini key

The phone has nowhere to put an API key. Reasoning, the illustration, and optional spoken audio run on the backend. When a Gemini key is added to the backend's Modal secret, that key is what the backend uses for those steps. This app already:

- sends `invoke` and waits for `status`, `card`, and `error`
- shows `models.reason` and `models.image` once the card names them
- shows a text card when `image_url` is null (image billing off)
- speaks `speech_text` when `audio_url` is null

The backend reads it as `GEMINI_API_KEY` (`backend/app/config.py`). Do not put the key in this folder.

## Run

Open `ios/MetaLab.xcodeproj` in Xcode 26, set your team, and run on a phone that is paired to the glasses with the Meta AI app in Developer Mode. The backend field takes a `wss://` URL.

`Hey Meta, start MetaLab` is configured in the Wearables Developer Center, not in this binary. The app name to avoid is anything with "AI" in the spoken phrase. MetaLab does not have that.

## What the tests cover

`ios/test.sh` checks the capture order (camera stops before the lens, speech still runs with the display off), the WebSocket messages, https-only lens images, and the reconnect rules. With Swift installed it also runs `MetaLabCore` unit tests.

## Privacy

One frame and one clip, only after the wearer asks. Both stay in memory and are dropped when the card or the error comes back. "Keep a sample frame" is off unless someone turns it on to collect pages for the reading-accuracy script.
