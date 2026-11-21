# 03. What a phone photo tells, before and after `PhotoField`

A photo from a phone carries hidden data: the phone model, the time and often the **GPS position**
where it was taken. A selfie taken at home says where the student lives. Here you read that data
out of a photo, push the photo through issue 006's `PhotoField`, and check that only clean pixels
are left: smaller, upright, and with no EXIF at all.

Do it after issue 006, step 2 (`config/photos.py` exists). Takes 10 minutes.

## Setup

You need a photo with EXIF data. Either:

- **a real one**: take a photo with your phone with location turned on, send it to your laptop
  *as a file* (AirDrop, a cable, "send as document"; most chat apps strip EXIF themselves), and
  save it as `var/phone.jpg`. `var/` is git-ignored: it never gets committed. Or
- **a made-up one**, like the run below: a 4000×3000 picture of noise (so it is as big as a real
  one), with EXIF that says "turn me" and a GPS position on a square in Avezzano.

Open the shell with `uv run python manage.py shell`. To make the made-up photo:

```pycon
>>> from PIL import Image, ExifTags
>>> exif = Image.Exif()
>>> exif[ExifTags.Base.Make] = "Phone Maker"
>>> exif[ExifTags.Base.Orientation] = 6
>>> exif[ExifTags.IFD.GPSInfo] = {ExifTags.GPS.GPSLatitudeRef: "N", ExifTags.GPS.GPSLatitude: (42.0, 1.0, 51.0), ExifTags.GPS.GPSLongitudeRef: "E", ExifTags.GPS.GPSLongitude: (13.0, 25.0, 34.0)}
>>> photo = Image.effect_noise((4000, 3000), 40).convert("RGB")
>>> photo.save("var/phone.jpg", exif=exif, quality=95)
```

`ls -l var/phone.jpg` says `9792868` bytes: almost 10 MB, like a real phone photo.

## Steps

### 1. Read what the photo tells

```pycon
>>> from PIL import Image, ExifTags
>>> original = Image.open("var/phone.jpg")
>>> original.size
(4000, 3000)
>>> {ExifTags.TAGS[tag]: value for tag, value in original.getexif().items()}
{'Orientation': 6, 'GPSInfo': 62, 'Make': 'Phone Maker'}
>>> {ExifTags.GPSTAGS[tag]: value for tag, value in original.getexif().get_ifd(ExifTags.IFD.GPSInfo).items()}
{'GPSLatitudeRef': 'N', 'GPSLatitude': (42.0, 1.0, 51.0), 'GPSLongitudeRef': 'E', 'GPSLongitude': (13.0, 25.0, 34.0)}
```

42° 1′ 51″ N, 13° 25′ 34″ E: type `42°1'51"N 13°25'34"E` into a map and you are standing in the
square. A real phone photo shows much more (date, lens, altitude, software).

### 2. Send it through `PhotoField`

This is what a form does with an upload (`request.FILES` holds a file like this one):

```pycon
>>> from django.core.files.uploadedfile import SimpleUploadedFile
>>> from config.photos import PhotoField
>>> upload = SimpleUploadedFile("IMG_0042.jpg", open("var/phone.jpg", "rb").read())
>>> upload.size
9792868
>>> cleaned = PhotoField().clean(upload)
>>> cleaned.name, cleaned.size
('photo.jpg', 192216)
```

### 3. Read what is left

```pycon
>>> after = Image.open(cleaned)
>>> after.size, after.format
((768, 1024), 'JPEG')
>>> dict(after.getexif())
{}
```

### 4. Something that isn't a photo

```pycon
>>> PhotoField().clean(SimpleUploadedFile("notes.jpg", b"%PDF-1.7 not a photo"))
Traceback (most recent call last):
  ...
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x10843c2c0>

The above exception was the direct cause of the following exception:
  ...
django.core.exceptions.ValidationError: ['Upload a valid image. The file you uploaded was either not an image or a corrupted image.']
```

## What just happened

- **The EXIF data is gone**, GPS included: `getexif()` is empty. `PhotoField` never stores the
  uploaded file. It reads the pixels and writes a *new* JPEG without passing `exif=`, so nothing
  of the original's extra data survives (issue 006, step 2).
- **The name is gone too**: `IMG_0042.jpg` became `photo.jpg`. A file name can say who or where.
- **4000×3000 became 768×1024, not 1024×768.** Orientation 6 means "the camera was held upright;
  turn the picture 90° to show it". `exif_transpose` turns the pixels *before* the EXIF note is
  dropped, then `thumbnail` shrinks the long side to 1024 px.
- **9.8 MB became 192 KB**: the server stores and sends 50 times less. (A real photo shrinks less
  than noise does, but still a lot.)
- **A renamed PDF is refused** by Django's `ImageField` (the `super().to_python()` call): Pillow
  can't open it, and the form shows the message in step 4 next to the field.

## Try this

1. In `config/photos.py`, replace `upright = ImageOps.exif_transpose(image)` with
   `upright = image` and repeat step 2: the size is `(1024, 768)`, a portrait photo lying on its
   side. Run `uv run pytest tests/config/test_photos.py`: the sideways test fails. Undo the change.
2. Try a file over 10 MB (a bigger noise image, or any big file renamed to `.jpg`):
   `ValidationError: ['The photo is bigger than 10 MB.']`, before Pillow even opens it.
3. After issue 008, register with your real phone photo and open the stored file
   (`var/media/photos/users/photo….jpg`) in your computer's image viewer. Its info panel
   (macOS Preview: Tools → Show Inspector; Windows: Properties → Details) shows no location.

## Belongs to

- [Issue 006](../../issues/006-photos.md), steps 2 and 3 (the field and its tests); used by 008,
  009, 010 and the admin.
- SPEC.md §2 #13 and §6.8.
