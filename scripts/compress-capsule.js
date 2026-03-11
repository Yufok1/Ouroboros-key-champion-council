const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const root = process.cwd();
const sourcePath = path.join(root, 'capsule', 'champion_gen8.py');
const outputPath = path.join(root, 'capsule', 'capsule.gz');

if (!fs.existsSync(sourcePath)) {
    console.log('No capsule/champion_gen8.py found, skipping compression');
    process.exit(0);
}

const data = zlib.gzipSync(fs.readFileSync(sourcePath));
fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, data);
console.log('Compressed capsule:', data.length, 'bytes');
console.log('Source:', sourcePath);
console.log('Output:', outputPath);
