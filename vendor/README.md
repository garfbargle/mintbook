# Vendored upstream snapshots

This directory preserves the small upstream sources that Mintbook directly
adapts. Each snapshot records its repository and immutable Git commit. Keeping
these files in-tree makes the build and its provenance inspectable even if an
upstream URL later changes or disappears.

Only the relevant, permissively licensed pieces are vendored. Large external
drivers and projects used as separately installed dependencies remain links in
the documentation.
