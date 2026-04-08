export default function ActionButton({ onClick, disabled, variant = 'default', children }) {
  const className = variant === 'primary' ? 'btn-primary'
    : variant === 'danger' ? 'btn-delete'
    : ''

  return (
    <button className={className} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  )
}