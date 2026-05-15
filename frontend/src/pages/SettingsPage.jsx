/**
 * SettingsPage — Page for ComfyUI connection settings.
 *
 * Will allow configuring server URL, workflow JSON, and node mapping.
 */

function SettingsPage() {
  return (
    <div>
      <h2 className="text-lg font-semibold text-white">Settings</h2>
      <p className="mt-2 text-sm text-gray-500">
        Configure ComfyUI connection and workflow settings.
      </p>
    </div>
  );
}

export default SettingsPage;