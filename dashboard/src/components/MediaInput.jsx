import React, { useState } from 'react';
import { Youtube, Upload, FileVideo, X, Gamepad2, Mic } from 'lucide-react';

const LAYOUTS = [
    { id: 'zoom', label: 'Zoom', hint: 'Big gameplay, blurred edges' },
    { id: 'fill', label: 'Full screen', hint: 'Center crop, fills the phone' },
    { id: 'fit', label: 'Whole screen', hint: 'Everything visible, smaller' },
];

const loadPref = (key, fallback) => {
    try {
        const v = localStorage.getItem(key);
        return v === null ? fallback : JSON.parse(v);
    } catch {
        return fallback;
    }
};

export default function MediaInput({ onProcess, isProcessing }) {
    const [mode, setMode] = useState('url'); // 'url' | 'file'
    const [url, setUrl] = useState('');
    const [file, setFile] = useState(null);
    const [contentType, setContentType] = useState(() => loadPref('openshorts_content_type', 'default'));
    const [layout, setLayout] = useState(() => loadPref('openshorts_gaming_layout', 'zoom'));
    const [videoAnalysis, setVideoAnalysis] = useState(() => loadPref('openshorts_video_analysis', true));

    const savePref = (key, value, setter) => {
        setter(value);
        try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
    };

    const options = contentType === 'gaming'
        ? { content_type: 'gaming', layout, video_analysis: videoAnalysis }
        : { content_type: 'default' };

    const handleSubmit = (e) => {
        e.preventDefault();
        if (mode === 'url' && url) {
            onProcess({ type: 'url', payload: url, options });
        } else if (mode === 'file' && file) {
            onProcess({ type: 'file', payload: file, options });
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setFile(e.dataTransfer.files[0]);
            setMode('file');
        }
    };

    return (
        <div className="bg-surface border border-white/5 rounded-2xl p-6 animate-[fadeIn_0.6s_ease-out]">
            <div className="flex gap-4 mb-6 border-b border-white/5 pb-4">
                <button
                    onClick={() => setMode('url')}
                    className={`flex items-center gap-2 pb-2 px-2 transition-all ${mode === 'url'
                        ? 'text-primary border-b-2 border-primary -mb-[17px]'
                        : 'text-zinc-400 hover:text-white'
                        }`}
                >
                    <Youtube size={18} />
                    YouTube URL
                </button>
                <button
                    onClick={() => setMode('file')}
                    className={`flex items-center gap-2 pb-2 px-2 transition-all ${mode === 'file'
                        ? 'text-primary border-b-2 border-primary -mb-[17px]'
                        : 'text-zinc-400 hover:text-white'
                        }`}
                >
                    <Upload size={18} />
                    Upload File
                </button>
            </div>

            <form onSubmit={handleSubmit}>
                {mode === 'url' ? (
                    <div className="space-y-4">
                        <input
                            type="url"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            placeholder="https://www.youtube.com/watch?v=..."
                            className="input-field"
                            required
                        />
                    </div>
                ) : (
                    <div
                        className={`border-2 border-dashed rounded-xl p-8 text-center transition-all ${file ? 'border-primary/50 bg-primary/5' : 'border-zinc-700 hover:border-zinc-500 bg-white/5'
                            }`}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={handleDrop}
                    >
                        {file ? (
                            <div className="flex items-center justify-center gap-3 text-white">
                                <FileVideo className="text-primary" />
                                <span className="font-medium">{file.name}</span>
                                <button
                                    type="button"
                                    onClick={() => setFile(null)}
                                    className="p-1 hover:bg-white/10 rounded-full"
                                >
                                    <X size={16} />
                                </button>
                            </div>
                        ) : (
                            <label className="cursor-pointer block">
                                <input
                                    type="file"
                                    accept="video/*"
                                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                                    className="hidden"
                                />
                                <Upload className="mx-auto mb-3 text-zinc-500" size={24} />
                                <p className="text-zinc-400">Click to upload or drag and drop</p>
                                <p className="text-xs text-zinc-600 mt-1">MP4, MOV up to 500MB</p>
                            </label>
                        )}
                    </div>
                )}

                <div className="mt-6 space-y-3">
                    <div className="grid grid-cols-2 gap-2">
                        <button
                            type="button"
                            onClick={() => savePref('openshorts_content_type', 'default', setContentType)}
                            className={`flex items-center justify-center gap-2 py-2 rounded-lg border text-sm transition-all ${contentType === 'default'
                                ? 'border-primary text-primary bg-primary/10'
                                : 'border-white/10 text-zinc-400 hover:text-white'
                                }`}
                        >
                            <Mic size={16} />
                            Talking / Podcast
                        </button>
                        <button
                            type="button"
                            onClick={() => savePref('openshorts_content_type', 'gaming', setContentType)}
                            className={`flex items-center justify-center gap-2 py-2 rounded-lg border text-sm transition-all ${contentType === 'gaming'
                                ? 'border-primary text-primary bg-primary/10'
                                : 'border-white/10 text-zinc-400 hover:text-white'
                                }`}
                        >
                            <Gamepad2 size={16} />
                            Gaming Stream
                        </button>
                    </div>

                    {contentType === 'gaming' && (
                        <div className="space-y-3 p-3 rounded-xl bg-white/5 border border-white/5">
                            <p className="text-xs text-zinc-400">Vertical layout</p>
                            <div className="grid grid-cols-3 gap-2">
                                {LAYOUTS.map((l) => (
                                    <button
                                        key={l.id}
                                        type="button"
                                        onClick={() => savePref('openshorts_gaming_layout', l.id, setLayout)}
                                        className={`py-2 px-1 rounded-lg border text-xs transition-all ${layout === l.id
                                            ? 'border-primary text-white bg-primary/10'
                                            : 'border-white/10 text-zinc-400 hover:text-white'
                                            }`}
                                    >
                                        <div className="font-medium">{l.label}</div>
                                        <div className="text-[10px] text-zinc-500 mt-0.5">{l.hint}</div>
                                    </button>
                                ))}
                            </div>
                            <label className="flex items-start gap-2 text-xs text-zinc-400 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={videoAnalysis}
                                    onChange={(e) => savePref('openshorts_video_analysis', e.target.checked, setVideoAnalysis)}
                                    className="mt-0.5"
                                />
                                <span>
                                    Let AI watch the gameplay (finds action even when you&apos;re not talking; slower and uses more Gemini credits)
                                </span>
                            </label>
                        </div>
                    )}
                </div>

                <button
                    type="submit"
                    disabled={isProcessing || (mode === 'url' && !url) || (mode === 'file' && !file)}
                    className="w-full btn-primary mt-6 flex items-center justify-center gap-2"
                >
                    {isProcessing ? (
                        <>
                            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            Processing Video...
                        </>
                    ) : (
                        <>
                            Generate Clips
                        </>
                    )}
                </button>
            </form>
        </div>
    );
}
