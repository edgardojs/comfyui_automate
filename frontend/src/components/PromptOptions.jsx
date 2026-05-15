/**
 * PromptOptions — Placeholder for prompt generation options.
 *
 * Will contain variation count selector, template selector,
 * negative profile selector, and category toggles.
 */

function PromptOptions() {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-5">
      <h2 className="mb-4 text-lg font-semibold text-white">
        Prompt Options
      </h2>
      <p className="text-sm text-gray-500">
        Configure generation options.
      </p>
    </div>
  );
}

export default PromptOptions;