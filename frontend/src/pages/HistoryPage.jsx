/**
 * HistoryPage — Page for viewing prompt generation history.
 *
 * Will display past generations with favorite toggles and re-generation options.
 */

function HistoryPage() {
  return (
    <div>
      <h2 className="text-lg font-semibold text-white">History</h2>
      <p className="mt-2 text-sm text-gray-500">
        View your past prompt generations.
      </p>
    </div>
  );
}

export default HistoryPage;