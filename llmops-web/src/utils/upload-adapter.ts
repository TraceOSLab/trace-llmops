import type { RequestOption, UploadRequest } from '@arco-design/web-vue'
/** Arco custom requests must return a request handle synchronously. */
export const uploadAdapter =
  (run: (option: RequestOption) => Promise<void>) =>
  (option: RequestOption): UploadRequest => {
    void run(option).catch((error) => option.onError(error))
    return {}
  }
