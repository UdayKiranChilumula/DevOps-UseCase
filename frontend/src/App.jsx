import { useEffect, useState } from "react";

export default function App() {
  const [services, setServices] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [fetching, setFetching] = useState(false); // For POST button state

  // Function to call /api/fetch
  const handleFetchClick = () => {
    setFetching(true);
    fetch("/api/fetch", { method: "POST" })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to trigger fetch");
        return res.json();
      })
      .then((data) => {
        console.log("Fetch triggered:", data);
        // Optionally, reload services after fetch completes
        loadServices();
      })
      .catch((err) => {
        setError(err.message);
      })
      .finally(() => setFetching(false));
  };

  // Separate function to load services
  const loadServices = () => {
    setLoading(true);
    fetch("/api/services")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch data");
        return res.json();
      })
      .then((data) => {
        setServices(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadServices();
  }, []);

  if (loading) return <div className="text-center mt-10 text-lg">Loading...</div>;
  if (error) return <div className="text-center mt-10 text-red-500">{error}</div>;

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <h1 className="text-3xl font-bold text-center mb-8">AWS Resources</h1>

      <div className="text-center mb-6">
        <button
          onClick={handleFetchClick}
          disabled={fetching}
          className={`px-4 py-2 rounded text-white ${
            fetching ? "bg-gray-400" : "bg-blue-500 hover:bg-blue-600"
          }`}
        >
          {fetching ? "Fetching..." : "Fetch Latest Data"}
        </button>
      </div>

      {Object.entries(services).map(([serviceName, records]) => (
        <div key={serviceName} className="mb-10">
          <h2 className="text-2xl font-semibold mb-4 capitalize">
            {serviceName.replace("_", " ")}
          </h2>
          {records.length === 0 ? (
            <p className="text-gray-500">No data available</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full bg-white border border-gray-300 rounded-lg shadow">
                <thead>
                  <tr className="bg-gray-200">
                    {Object.keys(records[0]).map((col) => (
                      <th key={col} className="px-4 py-2 border border-gray-300 text-left">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {records.map((row, idx) => (
                    <tr key={idx} className="hover:bg-gray-100">
                      {Object.values(row).map((val, i) => (
                        <td key={i} className="px-4 py-2 border border-gray-300">
                          {String(val)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
