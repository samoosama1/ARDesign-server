import { Link } from 'react-router-dom'
import { statusLabel } from '../statusLabels'

function statusClass(status) {
  return 'status status-' + status.toLowerCase()
}

/**
 * Compact catalog tile for one design. The card itself is a link to the
 * design's dedicated page (/designs/:id) where all the actions and the QR
 * code live; we pass the already-loaded `patent` via router state so the
 * detail page can render instantly while it revalidates.
 *
 * `locarnoTree` is the shape returned by GET /api/locarno; we use it to
 * resolve the patent's class/subclass codes to human-readable labels on
 * the client (the API only ships the codes).
 */
export default function DesignCard({ patent, locarnoTree }) {
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
    <Link
      to={`/designs/${patent.id}`}
      state={{ patent }}
      className="patent-card patent-card-link"
    >
      {patent.has_thumbnail ? (
        <div className="card-thumb">
          <img
            src={`/api/patents/${patent.id}/thumbnail`}
            alt={patent.model_filename}
            loading="lazy"
          />
        </div>
      ) : (
        <div className="card-thumb card-thumb-empty">
          <span aria-hidden="true">🖼</span>
          <span>No preview</span>
        </div>
      )}
      <h3>{patent.model_filename}</h3>
      <div className="card-status-row">
        <span className={statusClass(patent.status)}>{statusLabel(patent.status)}</span>
        {warningCount > 0 && (
          <span
            className="warning-badge"
            title={`${warningCount} converter warning${warningCount === 1 ? '' : 's'}`}
          >
            ⚠ {warningCount}
          </span>
        )}
      </div>
      {locarnoLine && <p className="meta locarno-line">{locarnoLine}</p>}
      <p className="meta">Type: {patent.file_type}</p>
      <p className="meta">Uploaded by: {patent.uploaded_by}</p>
      <p className="meta">{new Date(patent.uploaded_at).toLocaleDateString()}</p>

      <span className="card-open-cta">View details →</span>
    </Link>
  )
}