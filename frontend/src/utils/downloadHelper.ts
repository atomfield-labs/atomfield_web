/**
 * Triggers a client-side file download in the browser from a Blob or string content.
 */
export function triggerFileDownload(content: Blob | string, filename: string, mimeType = 'text/plain'): void {
  const blob = typeof content === 'string' ? new Blob([content], { type: mimeType }) : content;
  const downloadUrl = window.URL.createObjectURL(blob);
  const anchorElement = document.createElement('a');

  anchorElement.href = downloadUrl;
  anchorElement.download = filename;
  document.body.appendChild(anchorElement);
  anchorElement.click();
  anchorElement.remove();
  window.URL.revokeObjectURL(downloadUrl);
}
