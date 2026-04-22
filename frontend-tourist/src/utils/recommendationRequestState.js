let sharedRequestKey = ''
let sharedRequestId = ''
let sharedRequestPromise = null

export const getSharedRecommendationRequest = (key) => {
  if (!sharedRequestPromise || sharedRequestKey !== key || !sharedRequestId) return null
  return {
    key: sharedRequestKey,
    requestId: sharedRequestId,
    promise: sharedRequestPromise,
  }
}

export const setSharedRecommendationRequest = ({ key, requestId, promise }) => {
  sharedRequestKey = key
  sharedRequestId = requestId
  sharedRequestPromise = Promise.resolve(promise).finally(() => {
    if (sharedRequestId === requestId) {
      sharedRequestKey = ''
      sharedRequestId = ''
      sharedRequestPromise = null
    }
  })

  return sharedRequestPromise
}

export const clearSharedRecommendationRequest = (requestId) => {
  if (!requestId || sharedRequestId !== requestId) return
  sharedRequestKey = ''
  sharedRequestId = ''
  sharedRequestPromise = null
}
