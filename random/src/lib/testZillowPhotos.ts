// Test the Zillow photo parsing with your sample data
import { parseZillowPhotos } from './zillowPhotos';

const sampleData = `{"baseUrl":"https://photos.zillowstatic.com/fp/{photoKey}-p_e.jpg","communityBaseUrl":null,"photoData":[{"photoKey":"785792fc54a5ecc0448251a3f0e76052"},{"photoKey":"28cdb3f7280b53f3658a6b5d9c0152d9"},{"photoKey":"8703707b7f1f26165095fec5b50ba789"}],"communityPhotoData":null,"isStaticUrls":false}`;

console.log('Testing Zillow photo parsing...');
const photoUrls = parseZillowPhotos(sampleData);
console.log('Generated photo URLs:', photoUrls);

// Expected output should be:
// [
//   "https://photos.zillowstatic.com/fp/785792fc54a5ecc0448251a3f0e76052-p_e.jpg",
//   "https://photos.zillowstatic.com/fp/28cdb3f7280b53f3658a6b5d9c0152d9-p_e.jpg",
//   "https://photos.zillowstatic.com/fp/8703707b7f1f26165095fec5b50ba789-p_e.jpg"
// ]


