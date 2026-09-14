# Third-party notices

Mintbook is distributed under the MIT license in [`LICENSE`](LICENSE). The
following files include or are based on separately copyrighted work. Their
original license texts and the exact source revisions used here are kept
under `vendor/`.

## macbook8.1-bt-ssdc-fix

`bin/bt-install` and `config/initramfs/zz-acpi-ssdc-override` adapt the DSDT
override technique and implementation from Thomas Shirley's
[`macbook8.1-bt-ssdc-fix`](https://github.com/thomas-shirley/macbook8.1-bt-ssdc-fix).

Copyright (c) 2026 Thomas Shirley. Licensed under the MIT License. See
[`vendor/macbook8.1-bt-ssdc-fix/LICENSE`](vendor/macbook8.1-bt-ssdc-fix/LICENSE).

## WhiteSur GTK theme

`config/plank/WhiteSur/dock.theme` is derived from the Plank themes in
Vince Liuice's [`WhiteSur-gtk-theme`](https://github.com/vinceliuice/WhiteSur-gtk-theme).

Copyright (c) 2021 WhiteSur Developers. Licensed under the MIT License. See
[`vendor/WhiteSur-gtk-theme/COPYING`](vendor/WhiteSur-gtk-theme/COPYING).

## Nearby Share / Quick Share protobuf definitions

`vendor/nearby-protobufs/*.proto` are the Nearby Connections and Nearby
Sharing message definitions, taken verbatim from grishka's
[`NearDrop`](https://github.com/grishka/NearDrop) (itself released into the
public domain under the Unlicense), which carries them from Google's
[`nearby`](https://github.com/google/nearby) project.

Copyright (c) 2020 Google LLC. Licensed under the Apache License 2.0, whose
terms are stated in the header of each file. They are reference material for
`bin/mintbook_quickshare.py`: nothing here is compiled, and Mintbook has no
protobuf dependency — `bin/mintbook_protobuf.py` writes the wire format
directly. See [`vendor/nearby-protobufs/SOURCE.md`](vendor/nearby-protobufs/SOURCE.md).
