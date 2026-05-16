import { useState, useEffect, useCallback } from 'react'
import {
  fetchCharacters,
  createCharacter,
  updateCharacter,
  deleteCharacter,
} from '../api/client'
import ReferenceManager from '../components/ReferenceManager'
import CaptionEditor from '../components/CaptionEditor'
import TrainingConfig from '../components/TrainingConfig'

/**
 * CharactersPage — Manage character profiles for LoRA training.
 *
 * Features:
 * - List characters grouped by project
 * - Create new character profiles with auto-generated trigger tokens
 * - View character details
 * - Edit and delete characters
 */
function CharactersPage({ showToast }) {
  const [characters, setCharacters] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Dialog states
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showDetailId, setShowDetailId] = useState(null)
  const [detailTab, setDetailTab] = useState('references') // 'references' | 'captions' | 'training'
  const [showEditDialog, setShowEditDialog] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null) // stores the full character object

  // Create form state
  const [createForm, setCreateForm] = useState(defaultCreateForm())
  const [isCreating, setIsCreating] = useState(false)

  // Edit form state
  const [editForm, setEditForm] = useState({})
  const [isEditing, setIsEditing] = useState(false)

  const loadCharacters = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await fetchCharacters()
      setCharacters(data || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadCharacters()
  }, [loadCharacters])

  // Group characters by project
  const grouped = characters.reduce((acc, char) => {
    const key = char.project_name || 'Unassigned'
    if (!acc[key]) acc[key] = []
    acc[key].push(char)
    return acc
  }, {})

  // --- Create ---
  const handleCreate = useCallback(async () => {
    if (!createForm.project_name.trim() || !createForm.character_name.trim()) return
    setIsCreating(true)
    try {
      const payload = {
        project_name: createForm.project_name.trim(),
        character_name: createForm.character_name.trim(),
        species: createForm.species.trim() || null,
        character_class: createForm.character_class.trim() || null,
        weapon: createForm.weapon.trim() || null,
        armor: createForm.armor.trim() || null,
        color_palette: createForm.color_palette.trim() || null,
        art_style: createForm.art_style.trim() || null,
        target_sprite_size: createForm.target_sprite_size || null,
        target_perspective: createForm.target_perspective,
        animations: createForm.animations,
        trigger_token: createForm.trigger_token.trim() || null,
      }
      await createCharacter(payload)
      setShowCreateDialog(false)
      setCreateForm(defaultCreateForm())
      showToast('✅ Character created!')
      await loadCharacters()
    } catch (err) {
      showToast(`❌ ${err.message}`)
    } finally {
      setIsCreating(false)
    }
  }, [createForm, showToast, loadCharacters])

  // --- Edit ---
  const handleEdit = useCallback(async () => {
    if (!showEditDialog) return
    setIsEditing(true)
    try {
      // Only send fields that differ from the original character data
      const original = characters.find(c => c.character_id === showEditDialog)
      const updates = {}
      if (original) {
        for (const [key, value] of Object.entries(editForm)) {
          const originalValue = original[key] ?? ''
          const newValue = value ?? ''
          if (newValue !== originalValue) {
            // Send the new value, or null if empty
            updates[key] = value === '' ? null : value
          }
        }
      } else {
        // Fallback: send all fields if original not found
        for (const [key, value] of Object.entries(editForm)) {
          if (value !== null && value !== '') {
            updates[key] = value
          } else if (value === '') {
            updates[key] = null
          }
        }
      }
      // Only make the API call if there are actual changes
      if (Object.keys(updates).length === 0) {
        setShowEditDialog(null)
        setEditForm({})
        setIsEditing(false)
        return
      }
      await updateCharacter(showEditDialog, updates)
      setShowEditDialog(null)
      setEditForm({})
      showToast('✅ Character updated!')
      await loadCharacters()
    } catch (err) {
      showToast(`❌ ${err.message}`)
    } finally {
      setIsEditing(false)
    }
  }, [showEditDialog, editForm, showToast, loadCharacters, characters])

  // --- Delete ---
  const handleDelete = useCallback(async (characterId) => {
    try {
      await deleteCharacter(characterId)
      setDeleteTarget(null)
      showToast('🗑️ Character deleted')
      await loadCharacters()
    } catch (err) {
      showToast(`❌ ${err.message}`)
    }
  }, [showToast, loadCharacters])

  // --- Render helpers ---
  const selectedCharacter = showDetailId
    ? characters.find(c => c.character_id === showDetailId)
    : null

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-white">Characters</h2>
          <p className="mt-1 text-sm text-gray-400">
            Create character profiles for LoRA training and sprite generation.
          </p>
        </div>
        <button
          onClick={() => setShowCreateDialog(true)}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors cursor-pointer"
        >
          + New Character
        </button>
      </div>

      {/* Loading / Error */}
      {loading && <p className="text-gray-400 text-sm">Loading characters...</p>}
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">
          Error: {error}
        </div>
      )}

      {/* Empty state */}
      {!loading && characters.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          <p className="text-4xl mb-3">🧙</p>
          <p className="text-sm">No characters yet. Create one to get started!</p>
        </div>
      )}

      {/* Character list grouped by project */}
      {Object.entries(grouped).map(([project, chars]) => (
        <div key={project} className="mb-6">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
            {project}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {chars.map(char => (
              <div
                key={char.character_id}
                className="bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-gray-600 transition-colors cursor-pointer"
                onClick={() => setShowDetailId(char.character_id)}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h4 className="text-white font-medium">{char.character_name}</h4>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {char.species}{char.species && char.character_class ? ' · ' : ''}{char.character_class}
                    </p>
                  </div>
                  <span className="text-[10px] bg-gray-700 text-gray-300 px-2 py-0.5 rounded-full font-mono">
                    {char.trigger_token}
                  </span>
                </div>
                <div className="flex gap-2 mt-3 text-xs text-gray-500">
                  {char.weapon && <span>⚔️ {char.weapon}</span>}
                  {char.armor && <span>🛡️ {char.armor}</span>}
                  {char.art_style && <span>🎨 {char.art_style}</span>}
                </div>
                <div className="flex gap-1 mt-2 flex-wrap">
                  {(char.target_perspective || []).map(p => (
                    <span key={p} className="text-[10px] bg-gray-700/50 text-gray-400 px-1.5 py-0.5 rounded">
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* ===== Create Dialog ===== */}
      {showCreateDialog && (
        <div className="fixed inset-0 z-40 bg-black/60 flex items-center justify-center p-4" onClick={() => setShowCreateDialog(false)}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-white mb-4">New Character</h3>

            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Project Name *</label>
                  <input
                    type="text"
                    value={createForm.project_name}
                    onChange={e => setCreateForm(f => ({ ...f, project_name: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
                    placeholder="my_rpg"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Character Name *</label>
                  <input
                    type="text"
                    value={createForm.character_name}
                    onChange={e => setCreateForm(f => ({ ...f, character_name: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
                    placeholder="Grim the Dwarf"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Species</label>
                  <input
                    type="text"
                    value={createForm.species}
                    onChange={e => setCreateForm(f => ({ ...f, species: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
                    placeholder="dwarf"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Class</label>
                  <input
                    type="text"
                    value={createForm.character_class}
                    onChange={e => setCreateForm(f => ({ ...f, character_class: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
                    placeholder="rogue"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Weapon</label>
                  <input
                    type="text"
                    value={createForm.weapon}
                    onChange={e => setCreateForm(f => ({ ...f, weapon: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
                    placeholder="shortbow"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Armor</label>
                  <input
                    type="text"
                    value={createForm.armor}
                    onChange={e => setCreateForm(f => ({ ...f, armor: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
                    placeholder="studded leather"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Color Palette</label>
                  <input
                    type="text"
                    value={createForm.color_palette}
                    onChange={e => setCreateForm(f => ({ ...f, color_palette: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
                    placeholder="earth tones"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Art Style</label>
                  <input
                    type="text"
                    value={createForm.art_style}
                    onChange={e => setCreateForm(f => ({ ...f, art_style: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
                    placeholder="pixel art sprite"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1">Target Sprite Size</label>
                <select
                  value={createForm.target_sprite_size}
                  onChange={e => setCreateForm(f => ({ ...f, target_sprite_size: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
                >
                  <option value="">Default</option>
                  <option value="16x16">16×16</option>
                  <option value="32x32">32×32</option>
                  <option value="64x64">64×64</option>
                  <option value="128x128">128×128</option>
                  <option value="256x256">256×256</option>
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1">Target Perspectives</label>
                <div className="flex flex-wrap gap-2">
                  {['front', 'side', 'back', 'three-quarter'].map(p => (
                    <label key={p} className="flex items-center gap-1.5 text-sm text-gray-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={createForm.target_perspective.includes(p)}
                        onChange={e => {
                          if (e.target.checked) {
                            setCreateForm(f => ({ ...f, target_perspective: [...f.target_perspective, p] }))
                          } else {
                            setCreateForm(f => ({ ...f, target_perspective: f.target_perspective.filter(x => x !== p) }))
                          }}
                        }
                        className="accent-emerald-500"
                      />
                      {p}
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1">Animations</label>
                <div className="flex flex-wrap gap-2">
                  {['idle', 'walk', 'attack', 'hurt', 'death', 'cast'].map(a => {
                    const checked = createForm.animations.includes(a)
                    const toggle = (e) => {
                      if (e.target.checked) {
                        setCreateForm(f => ({ ...f, animations: [...f.animations, a] }))
                      } else {
                        setCreateForm(f => ({ ...f, animations: f.animations.filter(x => x !== a) }))
                      }
                    }
                    return (
                      <label key={a} className="flex items-center gap-1.5 text-sm text-gray-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={toggle}
                          className="accent-emerald-500"
                        />
                        {a}
                      </label>
                    )
                  })}
                </div>
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1">Trigger Token (auto-generated if blank)</label>
                <input
                  type="text"
                  value={createForm.trigger_token}
                  onChange={e => setCreateForm(f => ({ ...f, trigger_token: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white font-mono focus:border-emerald-500 focus:outline-none"
                  placeholder="my_project_grim_pixel_art_v1"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => { setShowCreateDialog(false); setCreateForm(defaultCreateForm()) }}
                className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={isCreating || !createForm.project_name.trim() || !createForm.character_name.trim()}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded-lg transition-colors cursor-pointer"
              >
                {isCreating ? 'Creating...' : 'Create Character'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== Detail View ===== */}
      {selectedCharacter && !showEditDialog && (
        <div className="fixed inset-0 z-40 bg-black/60 flex items-center justify-center p-4" onClick={() => setShowDetailId(null)}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-white">{selectedCharacter.character_name}</h3>
                <p className="text-xs text-gray-400 mt-0.5">
                  {selectedCharacter.project_name}
                  {selectedCharacter.species && ` · ${selectedCharacter.species}`}
                  {selectedCharacter.character_class && ` · ${selectedCharacter.character_class}`}
                </p>
              </div>
              <button
                onClick={() => setShowDetailId(null)}
                className="text-gray-400 hover:text-white text-xl leading-none cursor-pointer"
              >
                ✕
              </button>
            </div>

            {/* Trigger token */}
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 mb-4">
              <span className="text-xs text-gray-400">Trigger Token</span>
              <p className="text-emerald-400 font-mono text-sm mt-1">{selectedCharacter.trigger_token}</p>
            </div>

            {/* Details grid */}
            <div className="grid grid-cols-2 gap-3 text-sm mb-4">
              {detailField('Weapon', selectedCharacter.weapon)}
              {detailField('Armor', selectedCharacter.armor)}
              {detailField('Color Palette', selectedCharacter.color_palette)}
              {detailField('Art Style', selectedCharacter.art_style)}
              {detailField('Sprite Size', selectedCharacter.target_sprite_size)}
              {detailField('Species', selectedCharacter.species)}
            </div>

            {/* Perspectives */}
            <div className="mb-3">
              <span className="text-xs text-gray-400">Perspectives</span>
              <div className="flex gap-1 mt-1 flex-wrap">
                {(selectedCharacter.target_perspective || []).map(p => (
                  <span key={p} className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">{p}</span>
                ))}
              </div>
            </div>

            {/* Animations */}
            <div className="mb-4">
              <span className="text-xs text-gray-400">Animations</span>
              <div className="flex gap-1 mt-1 flex-wrap">
                {(selectedCharacter.animations || []).map(a => (
                  <span key={a} className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">{a}</span>
                ))}
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3 border-t border-gray-700 pt-4">
              <button
                onClick={() => {
                  setEditForm({
                    project_name: selectedCharacter.project_name || '',
                    character_name: selectedCharacter.character_name || '',
                    species: selectedCharacter.species || '',
                    character_class: selectedCharacter.character_class || '',
                    weapon: selectedCharacter.weapon || '',
                    armor: selectedCharacter.armor || '',
                    color_palette: selectedCharacter.color_palette || '',
                    art_style: selectedCharacter.art_style || '',
                    target_sprite_size: selectedCharacter.target_sprite_size || '',
                    trigger_token: selectedCharacter.trigger_token || '',
                  })
                  setShowEditDialog(selectedCharacter.character_id)
                }}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg transition-colors cursor-pointer"
              >
                ✏️ Edit
              </button>
              <button
                onClick={() => setDeleteTarget(selectedCharacter)}
                className="px-4 py-2 bg-red-900/50 hover:bg-red-800 text-red-300 text-sm rounded-lg transition-colors cursor-pointer"
              >
                🗑️ Delete
              </button>
            </div>

            {/* Reference Images / Captions */}
            <div className="border-t border-gray-700 mt-4 pt-4">
              {/* Tab bar */}
              <div className="flex gap-1 mb-3">
                <button
                  onClick={() => setDetailTab('references')}
                  className={`px-3 py-1.5 text-xs font-medium rounded-t transition-colors cursor-pointer ${
                    detailTab === 'references'
                      ? 'bg-gray-800 text-white border border-gray-700 border-b-gray-800'
                      : 'bg-gray-900 text-gray-400 hover:text-white border border-transparent'
                  }`}
                >
                  📸 References
                </button>
                <button
                  onClick={() => setDetailTab('captions')}
                  className={`px-3 py-1.5 text-xs font-medium rounded-t transition-colors cursor-pointer ${
                    detailTab === 'captions'
                      ? 'bg-gray-800 text-white border border-gray-700 border-b-gray-800'
                      : 'bg-gray-900 text-gray-400 hover:text-white border border-transparent'
                  }`}
                >
                  ✏️ Captions
                </button>
                <button
                  onClick={() => setDetailTab('training')}
                  className={`px-3 py-1.5 text-xs font-medium rounded-t transition-colors cursor-pointer ${
                    detailTab === 'training'
                      ? 'bg-gray-800 text-white border border-gray-700 border-b-gray-800'
                      : 'bg-gray-900 text-gray-400 hover:text-white border border-transparent'
                  }`}
                >
                  🎯 Training
                </button>
              </div>

              {/* Tab content */}
              {detailTab === 'references' && (
                <ReferenceManager characterId={selectedCharacter.character_id} showToast={showToast} />
              )}
              {detailTab === 'captions' && (
                <CaptionEditor characterId={selectedCharacter.character_id} showToast={showToast} />
              )}
              {detailTab === 'training' && (
                <TrainingConfig characterId={selectedCharacter.character_id} showToast={showToast} />
              )}
            </div>
          </div>
        </div>
      )}

      {/* ===== Edit Dialog ===== */}
      {showEditDialog && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => setShowEditDialog(null)}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-white mb-4">Edit Character</h3>

            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Project Name</label>
                  <input type="text" value={editForm.project_name ?? ''} onChange={e => setEditForm(f => ({ ...f, project_name: e.target.value }))} className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Character Name</label>
                  <input type="text" value={editForm.character_name ?? ''} onChange={e => setEditForm(f => ({ ...f, character_name: e.target.value }))} className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Species</label>
                  <input type="text" value={editForm.species ?? ''} onChange={e => setEditForm(f => ({ ...f, species: e.target.value }))} className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Class</label>
                  <input type="text" value={editForm.character_class ?? ''} onChange={e => setEditForm(f => ({ ...f, character_class: e.target.value }))} className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Weapon</label>
                  <input type="text" value={editForm.weapon ?? ''} onChange={e => setEditForm(f => ({ ...f, weapon: e.target.value }))} className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Armor</label>
                  <input type="text" value={editForm.armor ?? ''} onChange={e => setEditForm(f => ({ ...f, armor: e.target.value }))} className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Color Palette</label>
                  <input type="text" value={editForm.color_palette ?? ''} onChange={e => setEditForm(f => ({ ...f, color_palette: e.target.value }))} className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Art Style</label>
                  <input type="text" value={editForm.art_style ?? ''} onChange={e => setEditForm(f => ({ ...f, art_style: e.target.value }))} className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none" />
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Target Sprite Size</label>
                <select value={editForm.target_sprite_size ?? ''} onChange={e => setEditForm(f => ({ ...f, target_sprite_size: e.target.value }))} className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:border-emerald-500 focus:outline-none">
                  <option value="">Default</option>
                  <option value="16x16">16×16</option>
                  <option value="32x32">32×32</option>
                  <option value="64x64">64×64</option>
                  <option value="128x128">128×128</option>
                  <option value="256x256">256×256</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Trigger Token</label>
                <input type="text" value={editForm.trigger_token ?? ''} onChange={e => setEditForm(f => ({ ...f, trigger_token: e.target.value }))} className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white font-mono focus:border-emerald-500 focus:outline-none" />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => { setShowEditDialog(null); setEditForm({}) }} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors cursor-pointer">Cancel</button>
              <button onClick={handleEdit} disabled={isEditing} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded-lg transition-colors cursor-pointer">
                {isEditing ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== Delete Confirmation ===== */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => setDeleteTarget(null)}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl max-w-sm w-full p-6" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-white mb-2">Delete Character?</h3>
            <p className="text-sm text-gray-400 mb-4">
              This will permanently delete <span className="text-white font-medium">{deleteTarget.character_name}</span> and all associated files. This cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setDeleteTarget(null)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors cursor-pointer">Cancel</button>
              <button onClick={() => handleDelete(deleteTarget.character_id)} className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white text-sm font-medium rounded-lg transition-colors cursor-pointer">Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function detailField(label, value) {
  if (!value) return null
  return (
    <div>
      <span className="text-xs text-gray-400">{label}</span>
      <p className="text-sm text-white">{value}</p>
    </div>
  )
}

function defaultCreateForm() {
  return {
    project_name: '',
    character_name: '',
    species: '',
    character_class: '',
    weapon: '',
    armor: '',
    color_palette: '',
    art_style: '',
    target_sprite_size: '',
    target_perspective: ['front', 'side', 'back', 'three-quarter'],
    animations: ['idle', 'walk', 'attack', 'hurt'],
    trigger_token: '',
  }
}

export default CharactersPage