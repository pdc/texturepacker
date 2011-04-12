Data Files Used in Tests
========================

Some tests work by manipulating images and then comparing the result to
a sample image. So be careful about changing these images!

In particular:

- `redblack.png` and `greenyellow.png` are *palletized* images, used to
  test the ability of `SoucePack` and `Mixer` objects to cope with
  recipes using such images;

- `redgreen.png` is a combination of parts of those images, but is
  *not* in palletized format;