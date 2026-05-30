import ActionButton from './ActionButton'

function statusClass(status) {
  return 'status status-' + status.toLowerCase()
}

/**
 * Renders one design in a card grid. Action buttons are conditional on
 * ownership and status — handlers passed as props; the card itself owns
 * no API state.
 *
 * `locarnoTree` is the shape returned by GET /api/locarno; we use it to
 * resolve the patent's class/subclass codes to human-readable labels on
 * the client (the API only ships the codes).
 */
export default function DesignCard({
  patent,
  currentUserId,
  locarnoTree,
  onConvert,
  onView,
  onDownload,
  onQR,
  onDelete,
  onWarnings,
}) {
  const isOwner = patent.user_id === currentUserId
  const warningCount = patent.warnings?.length ?? 0

  let mainLabel = null
  let subLabel = null
  if (locarnoTree) {
    if (patent.locarno_main_class) {
      mainLabel = locarnoTree.main_classes.find(
        (m) => m.value === patent.locarno_main_class,
      )?.label || null
    }
    if (patent.locarno_subclass && patent.locarno_main_class) {
      subLabel = (locarnoTree.subclasses_by_main[patent.locarno_main_class] || [])
        .find((s) => s.value === patent.locarno_subclass)?.label || null
    }
  }
  const locarnoLine = [mainLabel, subLabel].filter(Boolean).join(' › ')

  return (
    <div className="patent-card">
      <h3>{patent.model_filename}</h3>
      <div className="card-status-row">
        <span className={statusClass(patent.status)}>{patent.status}</span>
        {warningCount > 0 && onWarnings && (
          <button
            type="button"
            className="warning-badge"
            onClick={() => onWarnings(patent)}
            title={`${warningCount} warning${warningCount === 1 ? '' : 's'} from the converter. Click for details.`}
          >
            ⚠ {warningCount}
          </button>
        )}
      </div>
      {locarnoLine && <p className="meta locarno-line">{locarnoLine}</p>}
      <p className="meta">Type: {patent.file_type}</p>
      <p className="meta">Uploaded by: {patent.uploaded_by}</p>
      <p className="meta">{new Date(patent.uploaded_at).toLocaleDateString()}</p>

      {isOwner && patent.status === 'UPLOADED' && onConvert && (
        <div className="card-actions">
          <ActionButton variant="primary" onClick={() => onConvert(patent.id)}>
            Convert
          </ActionButton>
        </div>
      )}
      {patent.status === 'CONVERTED' && (
        <div className="card-actions">
          {onView && (
            <ActionButton variant="primary" onClick={() => onView(patent)}>
              View
            </ActionButton>
          )}
          {onDownload && (
            <ActionButton onClick={() => onDownload(patent.id, patent.model_filename)}>
              Download
            </ActionButton>
          )}
          {onQR && (
            <ActionButton onClick={() => onQR(patent.id, patent.model_filename)}>
              QR Code
            </ActionButton>
          )}
        </div>
      )}
      {isOwner && patent.status === 'FAILED' && patent.file_type !== 'IMAGE' && onConvert && (
        <div className="card-actions">
          <ActionButton variant="primary" onClick={() => onConvert(patent.id)}>
            Retry
          </ActionButton>
        </div>
      )}
      {isOwner && onDelete && (
        <div className="card-actions">
          <ActionButton variant="danger" onClick={() => onDelete(patent.id)}>
            Delete
          </ActionButton>
        </div>
      )}
    </div>
  )
}
