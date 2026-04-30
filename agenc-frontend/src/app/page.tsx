"use client";
import { useState, useEffect } from "react";

export default function Home() {
  const [task, setTask] = useState("");
  const [reward, setReward] = useState("");
  const [logs, setLogs] = useState<{ time: string; msg: string }[]>([]);

  const addLog = (msg: string) => {
    setLogs((prev) => [
      ...prev,
      { time: new Date().toLocaleTimeString(), msg },
    ]);
  };

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch("http://127.0.0.1:8000/api/network-logs");
        const data = await res.json();

        if (data.new_event) {
          if (data.payload.type === "CLAIM") {
            addLog(`[*] Worker ${data.sender} claimed the task!`);
          } else if (data.payload.type === "COMPLETED_BOUNTY") {
            addLog(
              `[+] TASK COMPLETED by ${data.sender}. Result: ${data.payload.result}`,
            );
          }
        }
      } catch (err) {}
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  const submitBounty = async (e: React.FormEvent) => {
    e.preventDefault();
    addLog(`[!] Broadcasting bounty over AXL mesh: "${task}" for ${reward}`);

    await fetch("http://127.0.0.1:8000/api/bounty", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task, reward }),
    });
    setTask("");
  };

  return (
    <main className="min-h-screen bg-neutral-950 text-green-400 p-8 font-mono">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold mb-2 text-white">AgenC</h1>
        <p className="text-neutral-400 mb-8">
          Decentralized P2P Agent Bounty Mesh
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="bg-neutral-900 border border-neutral-800 p-6 rounded-lg h-[500px] overflow-y-auto">
            <h2 className="text-xl text-white mb-4 border-b border-neutral-800 pb-2">
              Mesh Network Logs
            </h2>
            <div className="space-y-2 text-sm text-neutral-300">
              {logs.map((log, i) => (
                <div key={i}>
                  <span className="text-neutral-500">[{log.time}]</span>{" "}
                  {log.msg}
                </div>
              ))}
              {logs.length === 0 && (
                <div className="text-neutral-600 animate-pulse">
                  Waiting for network activity...
                </div>
              )}
            </div>
          </div>

          <div className="bg-neutral-900 border border-neutral-800 p-6 rounded-lg h-fit">
            <h2 className="text-xl text-white mb-4 border-b border-neutral-800 pb-2">
              Post New Bounty
            </h2>
            <form onSubmit={submitBounty} className="space-y-4">
              <div>
                <label className="block text-sm text-neutral-400 mb-1">
                  Task Description
                </label>
                <textarea
                  className="w-full bg-neutral-950 border border-neutral-700 rounded p-2 text-white focus:border-green-400 focus:outline-none"
                  rows={3}
                  value={task}
                  onChange={(e) => setTask(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-neutral-400 mb-1">
                  Reward
                </label>
                <input
                  type="text"
                  className="w-full bg-neutral-950 border border-neutral-700 rounded p-2 text-white focus:border-green-400 focus:outline-none"
                  value={reward}
                  onChange={(e) => setReward(e.target.value)}
                  placeholder="e.g. 50 USDC"
                  required
                />
              </div>
              <button
                type="submit"
                className="w-full bg-green-500 hover:bg-green-400 text-neutral-950 font-bold py-2 px-4 rounded transition-colors"
              >
                Broadcast to Mesh
              </button>
            </form>
          </div>
        </div>
      </div>
    </main>
  );
}
