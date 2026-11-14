# AfterFire interface

## System

Hallmark Rim, adapted for a browser-based satellite atlas. The Explorer pairs the live geographic canvas with a filter panel and an observation window in UTC. Event pages give the map, composite dates, vegetation series and their source records room to read. The app uses English throughout.

## Tokens

[tokens.css](frontend/src/styles/tokens.css) defines the palette and type. The warm charcoal page and opaque warm panels frame the color in the map. Off-white is for primary text, warmer grey for secondary text. Orange marks the primary action and active selection. Ice blue marks source links and keyboard focus. Map colors retain their meanings in the observation legends.

Instrument Sans is used for interface and prose. Geist Mono is reserved for measurements, timestamps and coordinates. Text and figures remain selectable and are rendered separately from imagery.

## Composition

- Explorer keeps the map and UTC period together. Filters, search, layers and saved views are attached to the workspace.
- Recovery and recurrence lead with the event and its evidence. Methods, limitations and downloads follow in reading order.
- Dataset and published recovery records use ruled registers. Comparisons align equivalent measurements before presenting differences.
- A single top navigation identifies the active area. On compact screens it folds into a labeled menu, and the map keeps its own controls.

## Controls

Use square or minimally rounded controls with a visible edge or clear text label. Aim for a 44 px target for primary controls and show focus independently of hover. Use a quiet secondary style for options alongside the primary action. Disabled, selected and unavailable states include cues beyond color. Empty datasets and missing credentials have distinct copy.

## Motion and accessibility

Use motion to show a user-driven change, such as map movement or evidence playback. Honor reduced motion and increased contrast. Keep provider attribution visible on the map itself. Labels use sentence case and date ranges specify UTC where relevant.

## Hackathon review

| Signal in the demo | Revision |
| --- | --- |
| Animated badges and a generic error competed with actual fire observations. | The map leads. The app names the missing FIRMS key and links to the source status. |
| Repeated cards in the historical cases and datasets looked interchangeable. | Case rows lead with place and date. Dataset rows lead with product, resolution and acquisition cadence. |
| Pipeline timestamps and identifiers delayed the evidence in a recovery story. | The observed vegetation finding and before/after map lead. Quality, identifiers and telemetry are disclosed on demand. |
| Illustrative numbers and a chatbot badge gave unsupported findings a visual stamp of authority. | Removed illustrative figures, mark unavailable values explicitly, and identify language-model output where it is used. |

The main and secondary routes were checked at 320, 375, 768 and 1440 px. Populated workflows used isolated browser fixtures because this local instance has no published assessment or configured FIRMS key.
