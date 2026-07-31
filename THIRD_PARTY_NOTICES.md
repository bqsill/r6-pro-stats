# Third-party notices

This project bundles or derives from the work below. The MIT-licensed material
is redistributed here under the terms of its licence, reproduced in full.

---

## r6operators — operator icons

`r6stats/web/icons/*.svg` are taken unmodified from
[marcopixel/r6operators](https://github.com/marcopixel/r6operators).

```
MIT License

Copyright (c) 2021 Marco Vockner

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
```

---

## r6maps — room callout names and positions

`r6stats/web/maps/rooms.json` is derived from the room-label data in
[capajon/r6maps](https://github.com/capajon/r6maps) (callout names and
coordinates), transformed onto the Ubisoft blueprint frame.

```
The MIT License (MIT)
Copyright (c) 2016 Jon Capa

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

---

## Ubisoft — map blueprints and game imagery

Floor blueprints are **not redistributed with this project**. They are
downloaded from Ubisoft's own CDN by `python3 -m r6stats assets`, the same
files linked from each map's page on ubisoft.com.

Rainbow Six Siege, its maps, operators, and all related imagery are the
property of Ubisoft Entertainment. This project is an unofficial fan tool, not
affiliated with or endorsed by Ubisoft.

---

## SiegeGG — match statistics

All statistics are fetched at runtime from [SiegeGG](https://siege.gg)'s public
JSON endpoints and stored only in your local database. No statistics are
redistributed with this project. Requests are rate-limited to roughly three per
second and cached to avoid repeat traffic. Player photos and team logos shown
in the app are hot-linked from SiegeGG's CDN and remain their property.

If you maintain SiegeGG and would like this to stop or change, please open an
issue on the repository.
