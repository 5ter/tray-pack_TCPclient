// Shared browser helpers keep HTML error pages and parser failures out of UI messages.
async function fetchJson(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error('Cannot connect to the server. Check the network connection and try again.');
  }

  let responseText;
  try {
    responseText = await response.text();
  } catch {
    throw new Error('Could not read a response from the server. Please try again.');
  }

  let data = {};
  if (responseText) {
    try {
      data = JSON.parse(responseText);
    } catch {
      throw new Error(`The server returned an unexpected response (HTTP ${response.status}). Check the server connection.`);
    }
  }

  if (!response.ok) {
    const message = data && (data.error || data.message);
    throw new Error(typeof message === 'string' ? message : `The server request failed (HTTP ${response.status}).`);
  }
  return data;
}

function operatorErrorMessage(error) {
  return error instanceof Error
    ? error.message
    : 'An unexpected error occurred. Please try again or contact maintenance.';
}
