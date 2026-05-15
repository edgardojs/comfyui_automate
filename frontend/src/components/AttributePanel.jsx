/**
 * AttributePanel — Placeholder for the character attribute selection UI.
 *
 * Will contain dropdowns for each attribute category (class, species, weapon, etc.)
 * with lock toggles, randomize, and clear buttons.
 */

function AttributePanel() {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
      <h2 className="mb-4 text-lg font-semibold text-white">
        Character Attributes
      </h2>
      <p className="text-sm text-gray-500">
        Select attributes and generate sprite prompts.
      </p>
    </div>
  );
}

export default AttributePanel;