// Human-readable labels for the backend ConversionStatus enum. Keeps the raw
// SCREAMING_CASE values (and the old underscore-y IN_PROCESSING) out of the UI.
export const STATUS_LABELS = {
  UPLOADED: 'Uploaded',
  QUEUED: 'Queued',
  GENERATING: 'Generating',
  CONVERTING: 'Converting',
  CONVERTED: 'Converted',
  FAILED: 'Failed',
}

// Fall back to the raw value if the backend ever sends a status we don't map,
// so the UI degrades gracefully instead of rendering blank.
export function statusLabel(status) {
  return STATUS_LABELS[status] || status
}