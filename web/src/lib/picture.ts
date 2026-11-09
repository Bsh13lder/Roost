// A picture for a bot's screen (redesign P1, the avatar editor's Upload): any image the browser can
// read, cropped square from its middle and shrunk to PICTURE_SIDE px, so the upload stays far under
// the gateway's 512 KB (roost/constants.py AVATAR_PICTURE_MAX_BYTES).
export const PICTURE_SIDE = 256;
export const PICTURE_TYPE = "image/webp"; // a browser that cannot write WebP gives PNG instead
export const PICTURE_ACCEPT = "image/png,image/jpeg,image/webp,image/gif";
const PICTURE_QUALITY = 0.86;

export class PictureError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PictureError";
  }
}

async function readImage(file: Blob): Promise<ImageBitmap> {
  if (!file.type.startsWith("image/")) throw new PictureError("That file is not a picture. Pick a PNG, JPEG or WebP.");
  try {
    return await createImageBitmap(file);
  } catch {
    throw new PictureError("Roost could not read that picture. Try another one.");
  }
}

export async function shrinkPicture(file: Blob): Promise<Blob> {
  const image = await readImage(file);
  const canvas = document.createElement("canvas");
  canvas.width = PICTURE_SIDE;
  canvas.height = PICTURE_SIDE;
  const context = canvas.getContext("2d");
  if (!context) throw new PictureError("This browser cannot resize pictures. Try another browser.");
  const side = Math.min(image.width, image.height);
  context.drawImage(image, (image.width - side) / 2, (image.height - side) / 2, side, side, 0, 0, PICTURE_SIDE, PICTURE_SIDE);
  image.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, PICTURE_TYPE, PICTURE_QUALITY));
  if (!blob) throw new PictureError("Roost could not resize that picture. Try another one.");
  return blob;
}
