import { cp, mkdir, rm } from 'node:fs/promises';

const output = new URL('../dist/android/', import.meta.url);
const source = new URL('../static/', import.meta.url);

await rm(output, { recursive: true, force: true });
await mkdir(new URL('./static/', output), { recursive: true });
await cp(source, new URL('./static/', output), { recursive: true });
await cp(new URL('./index.html', source), new URL('./index.html', output));
await cp(new URL('./manifest.json', source), new URL('./manifest.json', output));
await cp(new URL('./sw.js', source), new URL('./sw.js', output));

console.log('Prepared the NOTTLE AI Android web bundle.');
