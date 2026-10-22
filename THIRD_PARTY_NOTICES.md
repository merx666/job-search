# Third-party notices

`data/city_codes_boss.json` was derived by the original Job Scout implementation from [eatmoreduck/boss-zhipin-scraper](https://github.com/eatmoreduck/boss-zhipin-scraper). Retain its attribution. Upstream license checked at [master/LICENSE](https://github.com/eatmoreduck/boss-zhipin-scraper/blob/master/LICENSE) on 2026-10-14:

MIT License

Copyright (c) 2026 eatmoreduck

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

`data/city_codes_liepin.json` retains the small mapping from the original local implementation. Codes are routing hints, not proof that returned jobs belong to the requested city; each result is checked separately. Unknown cities use the visible platform selector instead of guessed codes.

No third-party browser runtime, fonts, images, design-skill text or personal reports are bundled. Tabbit is an external dependency; its service and platform access remain subject to their respective terms. `openpyxl` is installed separately under its own MIT license.
