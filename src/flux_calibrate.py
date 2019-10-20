#!/usr/bin/env python

from astropy.io import fits
import ConfigParser
import glob
import header
import log
from pyraf import iraf
import obslog
import os
import utils


# ----------------------------------------------------------------------------------------------------------------------
def start(configfile):
    """
    Do a flux calibration.
    """
    logger = log.getLogger('flux_calibrate')

    path = os.getcwd()  # Store current working directory for later use.

    # Set up/prepare IRAF.
    iraf.gemini()
    iraf.gemtools()
    iraf.gnirs()
    iraf.onedspec()
    iraf.imutil()

    # Reset to default parameters the used IRAF tasks.
    iraf.unlearn(iraf.gemini, iraf.gemtools, iraf.gnirs, iraf.imutil)

    # Prepare the IRAF package for GNIRS.
    # NSHEADERS lists the header parameters used by the various tasks in the GNIRS package (excluding headers values 
    # which have values fixed by IRAF or FITS conventions).
    iraf.nsheaders("gnirs",logfile=logger.root.handlers[0].baseFilename)

    # Set clobber to 'yes' for the script. This still does not make the gemini tasks overwritewrite files, so: YOU WILL 
    # LIKELY HAVE TO REMOVE FILES IF YOU RE_RUN THE SCRIPT.
    us_clobber=iraf.envget("clobber")
    iraf.reset(clobber='yes')
    
    logger.info("Parameters read from %s", configfile)

    config = ConfigParser.RawConfigParser()
    config.optionxform = str  # make options case-sensitive
    config.read(configfile)

    manualMode = config.getboolean('defaults', 'manualMode')
    overwrite = config.getboolean('defaults', 'overwrite')
    extractFullSlit = config.getboolean('extractSpectra1D', 'extractFullSlit')
    extractStepwise = config.getboolean('extractSpectra1D', 'extractStepwise')
    extractStepSize = config.getfloat('extractSpectra1D', 'extractStepSize')
    combinedsrc = config.get('runtimeFilenames', 'combinedsrc')
    combinedsky = config.get('runtimeFilenames', 'combinedsky')  # Viraja:  Not sure if this is required; surprising though
    extractRegularPrefix = config.get('runtimeFilenames', 'extractRegularPrefix')
    extractFullSlitPrefix = config.get('runtimeFilenames', 'extractFullSlitPrefix')
    extractStepwisePrefix = config.get('runtimeFilenames', 'extractStepwisePrefix')
    hLinePrefix = config.get('runtimeFilenames', 'hLinePrefix')
    dividedTelContinuumPrefix = config.get('runtimeFilenames', 'dividedTelContinuumPrefix')
    telluricPrefix = config.get('runtimeFilenames', 'telluricPrefix')
    bb_unscaled = config.get('runtimeFilenames', 'bb_unscaled')
    bb_scaled = config.get('runtimeFilenames', 'bb_scaled')
    fluxCalibPrefix = config.get('runtimeFilenames', 'fluxCalibPrefix')
    fluxCalibrationMethod = config.get('fluxCalibration', 'fluxCalibrationMethod')


    for scipath in config.options("ScienceDirectories"):
        
        if not config.getboolean("ScienceDirectories", scipath):  # only process directories that are marked True
            logger.info('Skipping flux calibaration in %s', scipath)
            continue

        logger.info(' ------------------ ')
        logger.info('| Flux Calibration |')
        logger.info(' ------------------ ')

        scipath += '/Intermediate'
        iraf.chdir(scipath)
        logger.info('%s', scipath)

        if fluxCalibrationMethod == 'fluxcalibrator':
            stdpath = '../Standard/Intermediate'
            if not os.path.exists(stdpath):
                logger.error('fluxCalibrationMethod is fluxcalibrator but could not find Standard star directory')
                raise SystemExit
        elif fluxCalibrationMethod == 'telluricapproximate':
            stdpath = '../Telluric/Intermediate'
            if not os.path.exists(stdpath):
                logger.error('fluxCalibrationMethod is telluricapproximate but could not find Telluric directory')
                raise SystemExit
        else:
            logger.error('Uknown fluxCalibrationMethod')
            raise SystemExit
        logger.debug('stdpath: %s', stdpath)

        orders = utils.get_orders(scipath)
        sciroot = scipath + '/' + dividedTelContinuumPrefix + telluricPrefix + extractRegularPrefix + utils.nofits(combinedsrc)
        stdroot = stdpath + '/' + dividedTelContinuumPrefix + hLinePrefix + extractRegularPrefix + utils.nofits(combinedsrc)
        scifiles = ['%s_order%d.fits' % (sciroot, o) for o in orders]
        stdfiles = ['%s_order%d.fits' % (stdroot, o) for o in orders]
        logger.debug('scifiles: %s', scifiles)
        logger.debug('stdfiles: %s', stdfiles)
        utils.requires(scifiles + stdfiles)

        std_obslog = obslog.readcsv(stdpath + '/obslog.csv')
        firstfile = std_obslog.keys()[0]
        logger.debug('firstfile: %s', firstfile)
        std_name = std_obslog[firstfile]['OBJECT']
        logger.debug('Standard: %s', std_name)

        std_pars = utils.dictify(config.items(std_name))
        logger.debug('Standard pars: %s', std_pars)

        sci_exptime = fits.getheader(scifiles[0])['EXPTIME']
        std_exptime = fits.getheader(stdfiles[0])['EXPTIME']
        logger.debug('Sci Exptime: %s', sci_exptime)
        logger.debug('Std Exptime: %s', std_exptime)



        # Well, that's not correct!
        # The standard star exptime is showing as 300s, but the src_comb.fits shows it is really 5s.
        # Oh, the science NGC4736 spectra are being written in the Telluric directory.  That's not good.






        # TODO:  if extractionStepwise:


        utils.pause(True, 'STOP HERE *********************************************************************************')

        if fluxCalibrationMethod == 'fluxcalibrator':
            logger.error('Method not implemented')
            raise SystemExit

        elif fluxCalibrationMethod == 'telluricapproximate':

            # Convert magnitude to flux density for the telluric.
            # Derived spectrum (FLambda) for the telluric for each order.
            # Make a blackbody at the Telluric temperature for each order.
            # Get the scale for the blackbody to the telluric derived spectrum.
            # Blackbody scale (float) at each order.
            # Scale the blackbody to the telluric derived spectrum.
            # Scaled blackbody at each order.

            utils.pause('About to start flux calibration')

            stdTemperature = std_pars['Temperature']

            # EXPTIME keyword is the "Exposure time (s) for sum of all coadds"
            sciExptime = sci_header_info[os.path.basename(sci_telluricCorrected[0])]['EXPTIME']
            stdExptime = tel_header_info[os.path.basename(tel_dividedContinuum[0])]['EXPTIME']
            
            zeroMagnitudeFluxes = {}
            for order, zeroFlux in config.items('zeroMagnitudeFluxes'):
                zeroMagnitudeFluxes[int(order)] = zeroFlux

            for i in range(len(orders)):

                fluxCalibrationInput = os.path.basename(sci_telluricCorrected[i])+'[1]'
                sci_telluricCorrected_base_nofits = utils.nofits(os.path.basename(sci_telluricCorrected[i]))
                fluxCalibrationOutput_SEF = fluxCalibPrefix + \
                    sci_telluricCorrected_base_nofits[:sci_telluricCorrected_base_nofits.rfind('_')+1] + 'SEF.fits'
                logger.debug("fluxCalibrationOutput_SEF: %s", fluxCalibrationOutput_SEF)
                fluxCalibrationOutput_MEF = fluxCalibPrefix + os.path.basename(sci_telluricCorrected[i])
                logger.debug("fluxCalibrationOutput_MEF: %s", fluxCalibrationOutput_MEF)

                oldfiles = glob.glob(bb_unscaled+str(orders[i])+'.fits') + glob.glob(bb_scaled+str(orders[i])+'.fits') + \
                    glob.glob(fluxCalibrationOutput_SEF) + glob.glob(fluxCalibrationOutput_MEF)
                if overwrite:
                    logger.warning("Removing old %s%d.fits, %s%d.fits,", bb_unscaled, orders[i], bb_scaled, orders[i])
                    logger.warning("%s, and %s", fluxCalibrationOutput_SEF, fluxCalibrationOutput_MEF)
                    [os.remove(filename) for filename in oldfiles]
                else:
                    logger.warning("Output exists and -overwrite not set - skipping flux calibration for %d", orders[i])
                    logger.warning("of the telluric corrected science 1D source spectra.")
                    continue

                logger.info("Flux calibrating order %d of %s.", orders[i], os.path.basename(sci_telluricCorrected[i]))

                logger.info("Converting magnitude to flux density for the telluric.")
                # if the magnitude value in the configuration file is not empty
                if stdMagnitudes[i]:  
                    # Convert magnitude to erg/cm2/s/A, for a rough flux scaling
                    # Account for standard/science exposure times
                    logger.info("Performing absolute flux calibration accounting for the ratio of standard to science")
                    logger.info("exposure times.")
                    flambda = 10**(- float(stdMagnitudes[i])/2.5) * float(zeroMagnitudeFluxes[orders[i]]) * (stdExptime / sciExptime)
                    absolute_fluxcalib = True
                # if the magnitude value in the configuration file is empty, no absolute flux calibration is performed
                else:  
                    logger.info("Performing relative flux calibration accounting for the ratio of standard to science")
                    logger.info("exposure times.")
                    flambda = 1 * (stdExptime / sciExptime)
                    absolute_fluxcalib = False

                logger.info("Making a %dK blackbody.", stdTemperature)
                # First find the start and end wavelengths of the spectral order
                waveReferencePixel = iraf.hselect(images=tel_dividedContinuum[i]+'[1]', fields='CRPIX1', expr='yes',
                    missing='INDEF', mode='al', Stdout=1)
                waveReferencePixel = float_from_singleElementList(waveReferencePixel)

                waveReferenceValue = iraf.hselect(images=tel_dividedContinuum[i]+'[1]', fields='CRVAL1', expr='yes',
                    missing='INDEF', mode='al', Stdout=1)
                waveReferenceValue = float_from_singleElementList(waveReferenceValue)
                
                waveDelt = iraf.hselect(images=tel_dividedContinuum[i]+'[1]', fields='CD1_1', expr='yes',
                    missing='INDEF', mode='al', Stdout=1)
                waveDelt = float_from_singleElementList(waveDelt)

                waveStart = waveReferenceValue - (waveReferencePixel-1) * waveDelt

                ndimensions = iraf.hselect(images=tel_dividedContinuum[i]+'[1]', fields='NAXIS1', expr='yes',
                    missing='INDEF', mode='al', Stdout=1)
                ndimensions = float_from_singleElementList(ndimensions)
            
                waveEnd = waveStart + (ndimensions * waveDelt)
                
                # Then make a blackbody
                iraf.mk1dspec(input=bb_unscaled+str(orders[i]), output=bb_unscaled+str(orders[i]), ap=1, rv=0.0, z='no', 
                    title='', ncols=ndimensions, naps=1, header='', wstart = waveStart, wend=waveEnd, continuum=1000, 
                    slope=0.0, temperature=stdTemperature, fnu='no', lines='', nlines=0, profile='gaussian', peak=-0.5, 
                    gfwhm=20.0, lfwhm=20.0, seed=1, comments='yes', mode='ql')
                
                logger.info("Scaling the blackbody to the telluric magnitude.")
                if 3 <= orders[i] <= 5:
                    # Roughly scale blackbody for orders 3-5 to the respective magnitudes of the telluric
                    logger.info("Calculating the blackbody scale for order %d.", orders[i])
                    
                    meanCounts = iraf.imstat(images=bb_unscaled+str(orders[i]), fields="mean", lower='INDEF',
                        upper='INDEF', nclip=0, lsigma=3.0, usigma=3.0, binwidth=0.1, format='yes', cache='no', 
                        mode='al', Stdout=1)

                    blackbodyScaleFactor = flambda / float(meanCounts[1].replace("'",""))
                    logger.info("The blackbody scale factor for order %d is %e", orders[i], blackbodyScaleFactor)
                else:
                    # Scale blackbody for orders 6-8 to the previous order's scaled blackbody

                    # Ideally, waveEnd should be > waveStart.  If it is not, then there is something with the data that 
                    # is not necessarily a big problem, scientifically, but beeds some handling.  So, check for this
                    # and exit if there is no overlap between any two orders
                    
                    # First, find region of overlap with the previous order 
                    logger.info("Calculating the region of overlap of order %d with the previous order.", orders[i])
                    
                    # waveStart_previous is the first wavelength of the previous order (i.e, the short-wavelength end
                    # of the region of overlap)
                    
                    waveReferencePixel_previous = iraf.hselect(images=bb_unscaled+str(orders[i-1]), fields='CRPIX1', 
                        expr='yes', missing='INDEF', mode='al', Stdout=1)
                    waveReferencePixel_previous = float_from_singleElementList(waveReferencePixel_previous)
                    
                    waveReferenceValue_previous = iraf.hselect(images=bb_unscaled+str(orders[i-1]), fields='CRVAL1', 
                        expr='yes', missing='INDEF', mode='al', Stdout=1)
                    waveReferenceValue_previous = float_from_singleElementList(waveReferenceValue_previous)

                    waveDelt_previous = iraf.hselect(images=bb_unscaled+str(orders[i-1]), fields='CDELT1', expr='yes',
                        missing='INDEF', mode='al', Stdout=1)
                    waveDelt_previous = float_from_singleElementList(waveDelt_previous)

                    waveStart_previous = waveReferenceValue_previous - (waveReferencePixel_previous-1) * waveDelt_previous

                    # waveEnd_current is the last wavelength of the current order (i.e, the long-wavelength end of the
                    # region of overlap)
                    waveReferencePixel_current = iraf.hselect(images=bb_unscaled+str(orders[i]), fields='CRPIX1', 
                        expr='yes', missing='INDEF', mode='al', Stdout=1)
                    waveReferencePixel_current = float_from_singleElementList(waveReferencePixel_current)

                    waveReferenceValue_current = iraf.hselect(images=bb_unscaled+str(orders[i]), fields='CRVAL1', 
                        expr='yes', missing='INDEF', mode='al', Stdout=1)
                    waveReferenceValue_current = float_from_singleElementList(waveReferenceValue_current)

                    waveDelt_current = iraf.hselect(images=bb_unscaled+str(orders[i]), fields='CDELT1', expr='yes', 
                        missing='INDEF', mode='al', Stdout=1)
                    waveDelt_current = float_from_singleElementList(waveDelt_current)

                    waveStart_current = waveReferenceValue_current - (waveReferencePixel_current-1) * waveDelt_current

                    ndimensions_current = iraf.hselect(images=bb_unscaled+str(orders[i]), fields='NAXIS1', expr='yes', 
                        missing='INDEF', mode='al', Stdout=1)
                    ndimensions_current = float_from_singleElementList(ndimensions_current)

                    waveEnd_current = waveStart_current + (ndimensions_current * waveDelt_current)

                    if waveEnd_current < waveStart_previous:
                        logger.error("Orders %d and %d do not overlap in wavelength.", orders[i-1], [orderi])
                        logger.error("This is unusual and suggests that the grating was not at the expected position.")
                        logger.error("This may not be a problem for the scientific use of the data, but the script")
                        logger.error("cannot handle this and is not able to flux calibrate the spectral orders.") 
                        logger.error("Please plot the calibrated arc spectrum (plotted with different orders) to see")
                        logger.error("if the data cover the wavelength range you need.")
                        logger.error("Exiting script.\n")
                        raise SystemExit
                    else:
                        # Find the mean in the overlapping wavelength region (using the scaled blackbody of the
                        # previous order
                        oldfiles_temp = glob.glob('overlap_*')
                        [os.remove(filename) for filename in oldfiles_temp]
                        iraf.scopy(input=bb_unscaled+str(orders[i]), output='overlap_'+bb_unscaled+str(orders[i])+str(orders[i-1]),
                            w1=waveStart, w2=waveEnd, apertures='', beams='', bands='', apmodulus=0, 
                            format='multispec', renumber='no', offset=0, clobber='no', merge='no', rebin='yes', 
                            verbose='yes', mode='ql')
                        logger.debug("scopy 1 done")
                        iraf.scopy(input=bb_scaled+str(orders[i-1]), output='overlap_'+bb_scaled+str(orders[i])+str(orders[i-1]), 
                            w1=waveStart, w2=waveEnd, apertures='', beams='', bands='', apmodulus=0, 
                            format='multispec', renumber='no', offset=0, clobber='no', merge='no', rebin='yes', 
                            verbose='yes', mode='ql')
                        logger.debug("scopy 2 done")
                        meanCounts_overlap_bb_unscaled = iraf.imstat(images='overlap_'+bb_unscaled+str(orders[i])+str(orders[i-1]), 
                            fields='mean', lower='INDEF', upper='INDEF', nclip=0, lsigma=3.0, usigma=3.0, 
                            binwidth=0.1, format='yes', cache='no', mode='al', Stdout=1)
                        meanCounts_overlap_bb_unscaled = float(meanCounts_overlap_bb_unscaled[1].replace("'",""))
                        meanCounts_overlap_bb_scaled = iraf.imstat(images='overlap_'+bb_scaled+str(orders[i])+str(orders[i-1]), 
                            fields='mean', lower='INDEF', upper='INDEF', nclip=0, lsigma=3.0, usigma=3.0, binwidth=0.1, 
                            format='yes', cache='no', mode='al', Stdout=1)
                        meanCounts_overlap_bb_scaled = float(meanCounts_overlap_bb_scaled[1].replace("'",""))
                        
                        # Scale current blackbody to that for the previous order using ratio of means
                        blackbodyScaleFactor = meanCounts_overlap_bb_scaled / meanCounts_overlap_bb_unscaled
                        logger.info("The blackbody scale factor for order %d is %f", orders[i], blackbodyScaleFactor)

                iraf.imarith(operand1=bb_unscaled+str(orders[i]), op="*", operand2=blackbodyScaleFactor,
                    result=bb_scaled+str(orders[i]), title='',divzero=0.0, hparams='', pixtype='', calctype='',
                    verbose='yes', noact='no', mode='al')
                logger.info("Completed scaling the blackbody to the telluric magnitude.")

                logger.info("Applying the blackbody to telluric magnitude scaling fator to the telluric corrected")
                logger.info("science 1D source spectra.")
                
                iraf.imarith(operand1=fluxCalibrationInput, op="*", operand2=bb_scaled + str(orders[i]),
                    result=fluxCalibrationOutput_SEF, title='', divzero=0.0, hparams='', pixtype='', calctype='', 
                    verbose='yes', noact='no', mode='al')
                # Record flux density units in headers
                fluxcalib_units_in_headers(fluxCalibrationOutput_SEF, absolute_fluxcalib)

                iraf.wmef(input=fluxCalibrationOutput_SEF, output=fluxCalibrationOutput_MEF, extnames='',
                    phu=os.path.basename(sci_telluricCorrected[i]), verbose='yes', mode='al')
                
                if extractFullSlit:
                    '''
                    fluxCalibrationInput = os.path.basename()+'[1]'
                    fluxCalibrationOutput_SEF = fluxCalibPrefix + os.path.basename()
                    fluxCalibrationOutput_MEF = fluxCalibPrefix + os.path.basename()
                    iraf.imarith(operand1=fluxCalibrationInput, op="*", operand2=bb_scaled + str(orders[i]), 
                        result=fluxCalibrationOutput_SEF, title='', divzero=0.0, hparams='', pixtype='', 
                        calctype='', verbose='yes', noact='no', mode='al')
                    fluxcalib_units_in_headers("flamfull"+str(j), absolute_fluxcalib)
                    '''
                    pass
                if extractStepwise:
                    '''
                    fluxCalibrationInput = os.path.basename()+'[1]'
                    fluxCalibrationOutput_SEF = fluxCalibPrefix + os.path.basename()
                    fluxCalibrationOutput_MEF = fluxCalibPrefix + os.path.basename()
                    for k in range(1, steps):
                        iraf.imarith(operand1=fluxCalibrationInput, op="*", operand2=bb_scaled + str(orders[i]), 
                            result=fluxCalibrationOutput_SEF, title='', divzero=0.0, hparams='', pixtype='',
                            calctype='', verbose='yes', noact='no', mode='al')
                        fluxcalib_units_in_headers(fluxCalibrationInput, absolute_fluxcalib)
                    '''
                    pass
                logger.info("Completed applying the blackbody to telluric magnitude scaling fator to the telluric")
                logger.info("corrected science 1D source spectra.")
                
                logger.info("Completed flux calibrating order %d of %s.\n", orders[i], os.path.basename(sci_telluricCorrected[i]))

        else:
            logger.error("#######################################################################################")
            logger.error("#                                                                                     #")
            logger.error("#     ERROR in flux calibration: unknown flux calibration method. Exiting script.     #")
            logger.error("#                                                                                     #")
            logger.error("#######################################################################################")
            raise SystemExit

        logger.info("##############################################################################")
        logger.info("#                                                                            #")
        logger.info("#  COMPLETE - Flux calibration completed for                                 #")
        logger.info("#  %s", scipath)
        logger.info("#                                                                            #")
        logger.info("##############################################################################")


    os.chdir(path)  # Return to directory script was begun from.

    return


# ----------------------------------------------------------------------------------------------------------------------
def float_from_singleElementList(single_element_list):
    """
    Get the single element in a list and convert it into a float.
    """
    logger = log.getLogger('getFloat_from_singleElementList')
    
    return float(single_element_list[0].replace("'", ""))


# ----------------------------------------------------------------------------------------------------------------------
def fluxcalib_units_in_headers(image, abs_fluxcal):
    """
    Add appropriate flux calibration units (whether absolute or relative flux calibration) to the image headers after
    flux calibration is done. 
    """
    logger = log.getLogger('fluxcalib_units_in_headers')

    # This is so we know whether we did absolute or relative flux cal
    if abs_fluxcal:
        iraf.hedit(images=image, fields='FUNITS', value='erg/cm^2/s/A', add='yes', addonly='no', delete='no',
            verify='no', show='no', update='yes')
    else:
        iraf.hedit(images=image, fields='FUNITS', value='Flambda, relative', add='yes', addonly='no', delete='no',
            verify='no', show='no', update='yes')


# ----------------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    log.configure('gnirs-pype.log', filelevel='INFO', screenlevel='DEBUG')
    start('gnirs-pype.cfg')
