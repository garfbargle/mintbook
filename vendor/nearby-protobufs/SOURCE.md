# Nearby Share / Quick Share protobuf definitions

Google does not publish these as a protocol specification. They are the
message definitions the open implementations work from, taken verbatim from
grishka/NearDrop so that the field numbers in bin/mintbook_quickshare.py can
be checked against something rather than remembered.

    upstream   https://github.com/grishka/NearDrop
    path       NearbyShare/ProtobufSource/
    revision   8f1fdc7d5cbca4f540ff4fa87edcd578613be65f
    retrieved  2026-09-12

Nothing here is compiled. Mintbook has no protobuf dependency and no
generated code — bin/mintbook_protobuf.py encodes the wire format directly,
and these files are the reference for which field number means what. They
are kept so a future reader can verify a number without trusting a comment.

See ../README.md for how vendored sources are handled in this repository.
