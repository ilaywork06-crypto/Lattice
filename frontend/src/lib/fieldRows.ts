// Field definitions as edited in the UI (template editor, field-group editor),
// and their conversions to and from what the API sends and expects.
import type {
  FieldGroupField,
  FieldType,
  TemplateFieldIn,
  TemplateFieldOut,
} from '@/api/types'

export interface FieldRow extends TemplateFieldIn {
  uid: number
  expanded: boolean
}

let uid = 0

/** A deep copy of JSON data — also of Vue's reactive proxies, which
 *  structuredClone refuses. */
function copy<T>(value: T): T {
  return value === undefined ? value : (JSON.parse(JSON.stringify(value)) as T)
}

export function newFieldRow(ft: FieldType, label: string): FieldRow {
  return {
    uid: ++uid,
    expanded: true,
    id: null,
    key: null,
    label,
    field_type: ft,
    mode: 'item',
    required: false,
    config: ft === 'description' ? { min_length: 8 } : {},
    fixed_value: null,
  }
}

/**
 * Rows for a template's fields. `asNew` (duplicating) drops the ids so every
 * field is created afresh, and marks fixed files fields to copy their files.
 */
export function rowsFromTemplate(fields: TemplateFieldOut[], asNew = false): FieldRow[] {
  return fields.map((f) => ({
    uid: ++uid,
    expanded: false,
    id: asNew ? null : f.id,
    key: f.key,
    label: f.label,
    field_type: f.field_type,
    mode: f.mode,
    required: f.required,
    config: copy(f.config ?? {}),
    fixed_value: copy(f.fixed_value ?? null),
    copy_files_from:
      asNew && f.field_type === 'files' && f.mode === 'fixed' && f.files.length ? f.id : null,
  }))
}

export function rowsFromGroup(fields: FieldGroupField[]): FieldRow[] {
  return fields.map((f) => ({
    uid: ++uid,
    expanded: false,
    id: null,
    key: f.key,
    label: f.label,
    field_type: f.field_type,
    mode: f.mode,
    required: f.required,
    config: copy(f.config ?? {}),
    fixed_value: copy(f.fixed_value ?? null),
  }))
}

export function cleanFields(rows: FieldRow[], keepIds = true): TemplateFieldIn[] {
  return rows.map((f) => ({
    id: keepIds ? (f.id ?? null) : null,
    key: f.key ?? null,
    label: f.label.trim(),
    field_type: f.field_type,
    mode: f.mode,
    required: f.required,
    config: f.config,
    fixed_value: f.mode === 'fixed' ? f.fixed_value : null,
    ...(f.copy_files_from ? { copy_files_from: f.copy_files_from } : {}),
  }))
}
