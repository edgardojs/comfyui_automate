/**
 * GeneratePage — Main page for attribute selection and prompt generation.
 *
 * Will compose AttributePanel, PromptOptions, and PromptResults.
 */

function GeneratePage() {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <aside className="lg:col-span-1">
        {/* AttributePanel will go here */}
      </aside>
      <section className="lg:col-span-2">
        {/* PromptOptions + PromptResults will go here */}
      </section>
    </div>
  );
}

export default GeneratePage;