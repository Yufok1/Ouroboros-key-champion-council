/* Vendored from Three.js r160 examples/jsm/postprocessing/OutputPass.js with OutputShader inlined. */
(function (THREE) {
    if (!THREE) throw new Error('THREE namespace is required for OutputPass.js');
    var ColorManagement = THREE.ColorManagement;
    var RawShaderMaterial = THREE.RawShaderMaterial;
    var UniformsUtils = THREE.UniformsUtils;
    var LinearToneMapping = THREE.LinearToneMapping;
    var ReinhardToneMapping = THREE.ReinhardToneMapping;
    var CineonToneMapping = THREE.CineonToneMapping;
    var AgXToneMapping = THREE.AgXToneMapping;
    var ACESFilmicToneMapping = THREE.ACESFilmicToneMapping;
    var SRGBTransfer = THREE.SRGBTransfer;
    var Pass = THREE.Pass;
    var FullScreenQuad = THREE.FullScreenQuad;
const OutputShader = {

	name: 'OutputShader',

	uniforms: {

		'tDiffuse': { value: null },
		'toneMappingExposure': { value: 1 }

	},

	vertexShader: /* glsl */`
		precision highp float;

		uniform mat4 modelViewMatrix;
		uniform mat4 projectionMatrix;

		attribute vec3 position;
		attribute vec2 uv;

		varying vec2 vUv;

		void main() {

			vUv = uv;
			gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );

		}`,

	fragmentShader: /* glsl */`
	
		precision highp float;

		uniform sampler2D tDiffuse;

		#include <tonemapping_pars_fragment>
		#include <colorspace_pars_fragment>

		varying vec2 vUv;

		void main() {

			gl_FragColor = texture2D( tDiffuse, vUv );

			// tone mapping

			#ifdef LINEAR_TONE_MAPPING

				gl_FragColor.rgb = LinearToneMapping( gl_FragColor.rgb );

			#elif defined( REINHARD_TONE_MAPPING )

				gl_FragColor.rgb = ReinhardToneMapping( gl_FragColor.rgb );

			#elif defined( CINEON_TONE_MAPPING )

				gl_FragColor.rgb = OptimizedCineonToneMapping( gl_FragColor.rgb );

			#elif defined( ACES_FILMIC_TONE_MAPPING )

				gl_FragColor.rgb = ACESFilmicToneMapping( gl_FragColor.rgb );

			#elif defined( AGX_TONE_MAPPING )

				gl_FragColor.rgb = AgXToneMapping( gl_FragColor.rgb );

			#endif

			// color space

			#ifdef SRGB_TRANSFER

				gl_FragColor = sRGBTransferOETF( gl_FragColor );

			#endif

		}`

};

class OutputPass extends Pass {

	constructor() {

		super();

		//

		const shader = OutputShader;

		this.uniforms = UniformsUtils.clone( shader.uniforms );

		this.material = new RawShaderMaterial( {
			name: shader.name,
			uniforms: this.uniforms,
			vertexShader: shader.vertexShader,
			fragmentShader: shader.fragmentShader
		} );

		this.fsQuad = new FullScreenQuad( this.material );

		// internal cache

		this._outputColorSpace = null;
		this._toneMapping = null;

	}

	render( renderer, writeBuffer, readBuffer/*, deltaTime, maskActive */ ) {

		this.uniforms[ 'tDiffuse' ].value = readBuffer.texture;
		this.uniforms[ 'toneMappingExposure' ].value = renderer.toneMappingExposure;

		// rebuild defines if required

		if ( this._outputColorSpace !== renderer.outputColorSpace || this._toneMapping !== renderer.toneMapping ) {

			this._outputColorSpace = renderer.outputColorSpace;
			this._toneMapping = renderer.toneMapping;

			this.material.defines = {};

			if ( ColorManagement.getTransfer( this._outputColorSpace ) === SRGBTransfer ) this.material.defines.SRGB_TRANSFER = '';

			if ( this._toneMapping === LinearToneMapping ) this.material.defines.LINEAR_TONE_MAPPING = '';
			else if ( this._toneMapping === ReinhardToneMapping ) this.material.defines.REINHARD_TONE_MAPPING = '';
			else if ( this._toneMapping === CineonToneMapping ) this.material.defines.CINEON_TONE_MAPPING = '';
			else if ( this._toneMapping === ACESFilmicToneMapping ) this.material.defines.ACES_FILMIC_TONE_MAPPING = '';
			else if ( this._toneMapping === AgXToneMapping ) this.material.defines.AGX_TONE_MAPPING = '';

			this.material.needsUpdate = true;

		}

		//

		if ( this.renderToScreen === true ) {

			renderer.setRenderTarget( null );
			this.fsQuad.render( renderer );

		} else {

			renderer.setRenderTarget( writeBuffer );
			if ( this.clear ) renderer.clear( renderer.autoClearColor, renderer.autoClearDepth, renderer.autoClearStencil );
			this.fsQuad.render( renderer );

		}

	}

	dispose() {

		this.material.dispose();
		this.fsQuad.dispose();

	}

}
    THREE.OutputShader = OutputShader;
    THREE.OutputPass = OutputPass;
})(typeof THREE !== 'undefined' ? THREE : null);
