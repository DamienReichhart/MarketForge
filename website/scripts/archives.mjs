// Dependency-free readers for the archives the licence scripts look into:
// zip (Python wheels), gzipped tar (npm tarballs, Rust crates, Python sdists)
// and WebAssembly modules (their exported symbols).

import { gunzipSync, inflateRawSync } from 'node:zlib';

/** The files of a zip archive, as a map of name to a function that reads it. */
export function readZip(zip, label = 'zip archive') {
	let end = zip.length - 22;
	while (end >= 0 && zip.readUInt32LE(end) !== 0x06054b50) end--;
	if (end < 0) throw new Error(`${label} is not a zip archive`);
	const count = zip.readUInt16LE(end + 10);
	let pos = zip.readUInt32LE(end + 16);
	const files = new Map();
	for (let i = 0; i < count; i++) {
		if (zip.readUInt32LE(pos) !== 0x02014b50) throw new Error(`${label}: bad zip central directory`);
		const method = zip.readUInt16LE(pos + 10);
		const size = zip.readUInt32LE(pos + 20);
		const nameLength = zip.readUInt16LE(pos + 28);
		const extraLength = zip.readUInt16LE(pos + 30);
		const commentLength = zip.readUInt16LE(pos + 32);
		const offset = zip.readUInt32LE(pos + 42);
		const name = zip.toString('utf8', pos + 46, pos + 46 + nameLength);
		files.set(name, () => {
			const start = offset + 30 + zip.readUInt16LE(offset + 26) + zip.readUInt16LE(offset + 28);
			const data = zip.subarray(start, start + size);
			if (method === 0) return data;
			if (method === 8) return inflateRawSync(data);
			throw new Error(`${label}: ${name} uses zip compression method ${method}`);
		});
		pos += 46 + nameLength + extraLength + commentLength;
	}
	return files;
}

/** The regular files of a gzipped tar archive, as a map of path to contents. */
export function readTarGz(gz) {
	const tar = gunzipSync(gz);
	const files = new Map();
	let longName;
	for (let pos = 0; pos + 512 <= tar.length; ) {
		const header = tar.subarray(pos, pos + 512);
		if (header.every((b) => b === 0)) break;
		const field = (start, length) => header.toString('utf8', start, start + length).replace(/\0.*$/s, '');
		const size = Number.parseInt(field(124, 12).trim() || '0', 8);
		const type = field(156, 1) || '0';
		const prefix = field(345, 155);
		let name = longName ?? (prefix ? `${prefix}/${field(0, 100)}` : field(0, 100));
		longName = undefined;
		const data = tar.subarray(pos + 512, pos + 512 + size);
		if (type === 'L') longName = data.toString('utf8').replace(/\0.*$/s, '');
		else if (type === 'x') {
			const path = /\d+ path=([^\n]*)\n/.exec(data.toString('utf8'));
			if (path) longName = path[1];
		} else if (type === '0' || type === '7') files.set(name.replace(/^\.\//, ''), data);
		pos += 512 + Math.ceil(size / 512) * 512;
	}
	return files;
}

function leb128(bytes, pos) {
	let value = 0;
	let shift = 0;
	for (;;) {
		const byte = bytes[pos++];
		value += (byte & 0x7f) * 2 ** shift;
		shift += 7;
		if (byte < 0x80) return [value, pos];
	}
}

/** The names a WebAssembly module exports. */
export function wasmExports(wasm) {
	if (wasm.readUInt32LE(0) !== 0x6d736100) throw new Error('not a WebAssembly module');
	const names = [];
	let pos = 8;
	while (pos < wasm.length) {
		const id = wasm[pos++];
		const [size, start] = leb128(wasm, pos);
		if (id === 7) {
			let [count, p] = leb128(wasm, start);
			for (; count > 0; count--) {
				let length;
				[length, p] = leb128(wasm, p);
				names.push(wasm.toString('utf8', p, p + length));
				p += length + 1; // the name, then the export kind
				[, p] = leb128(wasm, p); // and its index
			}
		}
		pos = start + size;
	}
	return names;
}
