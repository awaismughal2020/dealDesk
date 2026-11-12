/** Client-side upload checks for usability only; the server re-checks everything by content. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ACCEPTED = [".pdf", ".txt"];

export function checkBriefFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED.some((extension) => name.endsWith(extension))) {
    return "Choose a PDF or a plain-text (.txt) file.";
  }
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) return "The file is larger than 10 MB.";
  return null;
}
