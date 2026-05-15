/**
 * PromptResults — Placeholder for displaying generated prompt pairs.
 *
 * Will show positive/negative prompt cards with copy buttons,
 * favorite toggle, and send-to-ComfyUI button.
 */

function PromptResults() {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
      <h2 className="mb-4 text-lg font-semibold text-white">
        Generated Prompts
      </h2>
      <p className="text-sm text-gray-500">
        Your positive and negative prompts will appear here.
      </p>
    </div>
  );
}

export default PromptResults;