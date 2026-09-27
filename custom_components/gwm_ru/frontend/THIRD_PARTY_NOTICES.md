# StarLine design adaptation

The remote card uses PNG artwork, vehicle layout, circular controls, smoke and blink animations from [Anonym-tsk/lovelace-starline-card](https://github.com/Anonym-tsk/lovelace-starline-card), commit bdf451f46d65863eae102b5b90ec4327bc4559a5, under GPL-3.0. The adapted gwm-vehicle-remote-card.js is distributed under GPL-3.0-only; see LICENSE.starline. Other integration files retain their existing licenses.

The original PNGs are embedded losslessly in STARLINE_ASSETS, named after the upstream files without the car_indication_ prefix. Both light and dark variants are included. No external asset requests are needed. The illustration is the upstream generic vehicle, not a model-specific rendering. GWM supplies vehicle states and commands; climate indication and responsive information tiles are additions.

## Source and license

- Original card: [Anonym-tsk/lovelace-starline-card](https://github.com/Anonym-tsk/lovelace-starline-card).
- Reference revision: [bdf451f46d65863eae102b5b90ec4327bc4559a5](https://github.com/Anonym-tsk/lovelace-starline-card/tree/bdf451f46d65863eae102b5b90ec4327bc4559a5).
- Included license: [LICENSE.starline](LICENSE.starline).
- Repository-wide notices: [THIRD_PARTY_NOTICES.md](../../../THIRD_PARTY_NOTICES.md).

## Acknowledgements / Благодарности

Спасибо **Anonym-tsk**, всем авторам и участникам **lovelace-starline-card** за исходную карточку, дизайн, графику и анимации. Их открытая работа стала основой нового оформления `gwm-vehicle-remote-card`.

Благодарим всех, кто участвовал в разработке, тестировании, документации, исправлении ошибок и улучшении исходного проекта, включая участников, не перечисленных здесь поимённо. Сведения об их вкладах доступны в истории исходного репозитория. Благодарности авторам других использованных проектов приведены в общих уведомлениях по ссылке выше.

## Adapted GWM card sources

The generic GWM dashboard cards and trip-card logic are adapted from [IndeecDen/ha-gwm-jolion](https://github.com/IndeecDen/ha-gwm-jolion), Copyright (c) 2026 IndeecDen, under the MIT License. See [LICENSE.ha-gwm-jolion](LICENSE.ha-gwm-jolion).
