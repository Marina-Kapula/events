// The photo editor: pick a photo (camera or gallery), then move, zoom and turn it
// inside a round frame. "Use photo" puts the cropped square back into the form's
// file input as a JPEG, so the server gets what the student saw.
//
// Markup (templates/photo_editor.html): a file input with data-photo-input, an
// <img data-photo-preview> and the <dialog id="photo-editor">.
(() => {
  const OUT = 1024; // the side of the saved photo, as config/photos.py MAX_SIDE
  const dialog = document.getElementById("photo-editor");
  const input = document.querySelector("[data-photo-input]");
  const preview = document.querySelector("[data-photo-preview]");
  if (!dialog || !input || !preview) return;
  const frame = dialog.querySelector("[data-frame]");
  const picture = dialog.querySelector("[data-picture]");
  const zoomSlider = dialog.querySelector("[data-zoom]");

  let image = null; // the loaded photo
  let turns = 0; // quarter turns clockwise
  let zoom = 1;
  let x = 0; // the photo's centre, from the frame's centre, in CSS pixels
  let y = 0;
  let lastFiles = null; // what the input held before, to restore on Cancel

  const side = () => frame.clientWidth;
  // The photo's width and height once turned.
  const turned = () =>
    turns % 2 ? [image.naturalHeight, image.naturalWidth] : [image.naturalWidth, image.naturalHeight];
  // At zoom 1 the photo just covers the frame.
  const scale = () => (side() / Math.min(...turned())) * zoom;

  function clamp() {
    const [w, h] = turned();
    const maxX = Math.max(0, (w * scale() - side()) / 2);
    const maxY = Math.max(0, (h * scale() - side()) / 2);
    x = Math.min(maxX, Math.max(-maxX, x));
    y = Math.min(maxY, Math.max(-maxY, y));
  }

  function draw() {
    clamp();
    picture.style.width = `${image.naturalWidth}px`;
    picture.style.height = `${image.naturalHeight}px`;
    picture.style.transform =
      `translate(-50%, -50%) translate(${x}px, ${y}px) rotate(${turns * 90}deg) scale(${scale()})`;
  }

  input.addEventListener("change", () => {
    const file = input.files[0];
    if (!file) return;
    const loaded = new Image();
    loaded.onload = () => {
      image = loaded;
      picture.src = loaded.src;
      turns = 0;
      zoom = 1;
      x = 0;
      y = 0;
      zoomSlider.value = "1";
      dialog.showModal();
      draw();
    };
    loaded.onerror = () => {
      // The browser can't show it (a rare format): send it as it is; the server checks it.
      preview.src = URL.createObjectURL(file);
      preview.classList.remove("hidden");
    };
    loaded.src = URL.createObjectURL(file);
  });

  zoomSlider.addEventListener("input", () => {
    zoom = Number(zoomSlider.value);
    draw();
  });
  dialog.querySelector("[data-turn]").addEventListener("click", () => {
    turns = (turns + 1) % 4;
    [x, y] = [-y, x];
    draw();
  });

  // Drag with one finger or the mouse; pinch with two fingers to zoom.
  const pointers = new Map();
  let start = null;
  frame.addEventListener("pointerdown", (event) => {
    frame.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, [event.clientX, event.clientY]);
    start = null;
  });
  frame.addEventListener("pointermove", (event) => {
    if (!pointers.has(event.pointerId)) return;
    const [oldX, oldY] = pointers.get(event.pointerId);
    pointers.set(event.pointerId, [event.clientX, event.clientY]);
    if (pointers.size === 1) {
      x += event.clientX - oldX;
      y += event.clientY - oldY;
    } else if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const distance = Math.hypot(a[0] - b[0], a[1] - b[1]);
      start ??= { distance, zoom };
      zoom = Math.min(4, Math.max(1, (start.zoom * distance) / start.distance));
      zoomSlider.value = String(zoom);
    }
    draw();
  });
  const release = (event) => {
    pointers.delete(event.pointerId);
    start = null;
  };
  frame.addEventListener("pointerup", release);
  frame.addEventListener("pointercancel", release);

  // Cancel (or Esc) keeps the photo chosen before, if any.
  const cancel = () => {
    input.files = lastFiles ?? new DataTransfer().files;
    dialog.close();
  };
  dialog.querySelector("[data-cancel]").addEventListener("click", cancel);
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    cancel();
  });

  dialog.querySelector("[data-use]").addEventListener("click", () => {
    const canvas = document.createElement("canvas");
    canvas.width = OUT;
    canvas.height = OUT;
    const context = canvas.getContext("2d");
    const k = OUT / side();
    context.fillStyle = "#fff";
    context.fillRect(0, 0, OUT, OUT);
    context.translate(OUT / 2 + x * k, OUT / 2 + y * k);
    context.rotate((turns * Math.PI) / 2);
    context.scale(scale() * k, scale() * k);
    context.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2);
    canvas.toBlob(
      (blob) => {
        const files = new DataTransfer();
        files.items.add(new File([blob], "photo.jpg", { type: "image/jpeg" }));
        input.files = files.files;
        lastFiles = input.files;
        preview.src = URL.createObjectURL(blob);
        preview.classList.remove("hidden");
        document.querySelectorAll("[data-photo-hide-when-chosen]").forEach((e) => e.remove());
        input.removeAttribute("required");
        dialog.close();
      },
      "image/jpeg",
      0.9,
    );
  });
})();
